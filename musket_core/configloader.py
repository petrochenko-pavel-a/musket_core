import importlib
import os
import yaml
import inspect

class Module:

    def __init__(self,dict):
        self.catalog={};
        self.orig={}
        self.entry=None
        for v in dict["types"]:
            t=Type(v,self,dict["types"][v]);
            if t.entry:
                self.entry=v;
            self.catalog[v.lower()]=t
            self.catalog[v] = t
            self.orig[v.lower()]=v
        self.pythonModule=importlib.import_module(dict["(meta.module)"])
        pass

    def register(self,pythonPath):
        pyMod=importlib.import_module(pythonPath)
        for x in dir(pyMod):
            tp=getattr(pyMod,x)
            if inspect.isclass(tp):
                init=getattr(tp, "__init__")
                gignature=inspect.signature(init)
                typeName=x
                tp=PythonType(typeName,gignature,tp)
                self.catalog[typeName.lower()] = tp
                self.catalog[typeName] = tp
                self.orig[typeName.lower()] = typeName
            if inspect.isfunction(tp):
                gignature = inspect.signature(tp)
                typeName = x
                tp = PythonFunction(gignature, tp)
                self.catalog[typeName.lower()] = tp
                self.catalog[typeName] = tp
                self.orig[typeName.lower()] = typeName
            pass
        pass

    def instantiate(self, dct, clear_custom=False, with_args=None):
        if with_args is None:
            with_args={}
        if self.entry:
            typeDefinition = self.catalog[self.entry];
            clazz = getattr(self.pythonModule, self.entry)
            args = typeDefinition.constructArgs(dct, clear_custom)
            return clazz(**args)

        if type(dct)==dict:
            result = []

            for v in dct:
                typeDefinition = self.catalog[v.lower()]
                if isinstance(typeDefinition,PythonType) or isinstance(typeDefinition,PythonFunction):
                    clazz=typeDefinition.clazz
                else:
                    if hasattr(self.pythonModule,v[0].upper()+v[1:]):
                        clazz = getattr(self.pythonModule, v[0].upper()+v[1:])
                    else: clazz=getattr(self.pythonModule, self.orig[v])

                args=typeDefinition.constructArgs(dct[v], clear_custom)
                allProps=typeDefinition.all()
                for v in with_args:
                    if v in allProps:
                        args[v]=with_args[v]
                if type(args)==dict:
                    result.append(clazz(**args))
                else:
                    result.append(clazz(args))
            return result


        return dct

class AbstractType:

    def __init__(self):
        self.name = None
        self.type = None
        self.module=None

    def positional(self):
        return []

    def all(self):
        return []

    def custom(self):
        return []

    def property(self, propName): None

    def constructArgs(self,dct,clearCustom=False):
        #for c in dct:
        if type(dct)==str or type(dct)==int:

            return dct

        if clearCustom:

            if isinstance(dct,dict) and "args" in dct:
                dct=dct["args"]
            if isinstance(dct,list):
                pos=self.positional()
                argMap={}
                for i in range(min(len(dct),len(pos))):
                    prop = pos[i]
                    value = dct[i]
                    if self.module != None and prop.propRange in self.module.catalog:
                        propRange = self.module.catalog[prop.propRange]
                        if propRange.isAssignableFrom("Layer"):
                            value = self.module.instantiate(value, True,{})[0]
                    if isinstance(prop,str):
                        argMap[prop]=value
                    else: argMap[prop.name]=value
                dct=argMap
                pass
            if isinstance(dct, dict):
                r=dct.copy()
                ct=self.custom()
                for v in dct:
                    if v in ct:
                        del r[v]
                return r
        return dct

    def isAssignableFrom(self, typeName):
        if self.name == typeName:
            return True
        elif self.type == None:
            return False
        elif self.type == typeName:
            return True
        elif self.type.lower() in self.module.catalog:
            return self.module.catalog[self.type.lower()].isAssignableFrom(typeName)
        else:
            return False


class PythonType(AbstractType):

    def __init__(self,type:str,s:inspect.Signature,clazz):
        super(PythonType, self).__init__()
        args=[p for p in s.parameters][1:]
        self.args=args
        self.clazz=clazz
        self.type = type

    def positional(self):
        return self.args

    def all(self):
        return self.args

class PythonFunction(AbstractType):

    def __init__(self,s:inspect.Signature,clazz):
        super(PythonFunction,self).__init__()
        if hasattr(clazz,"args"):
            args=[p for p in clazz.args if "input" not in p]
        else: args=[p for p in s.parameters if "input" not in p]
        self.args=args

        def create(*args,**kwargs):
            if len(args) == 1 and args[0] is None:
                args = []
            mm = kwargs.copy()
            for i in range(len(args)):
                mm[self.args[i]]=args[i]
            def res(i):
                if i is not None:
                    mm["input"]=i
                return clazz(**mm)
            return res
        self.clazz=create

    def positional(self):
        return self.args

    def all(self):
        return self.args

class Type(AbstractType):


    def __init__(self,name:str,m:Module,dict):
        super(Type,self).__init__()
        self.name = name
        self.module=m;
        self.properties={};
        self.entry="(meta.entry)" in dict
        if type(dict)!=str:
            self.type=dict["type"]
            if 'properties' in dict:
                for p in dict['properties']:
                    pOrig=p;
                    if p[-1]=='?':
                        p=p[:-1]
                    self.properties[p]=Property(p,self,dict['properties'][pOrig])
        else:
            self.type = dict
        pass

    def alias(self,name:str):
        if name in self.properties:
            p:Property=self.properties[name]
            if p.alias!=None:
                return p.alias
        return name

    def custom(self):
        c= {v for v in self.properties if self.properties[v].custom}
        if self.type.lower() in self.module.catalog:
            c = c.union(self.module.catalog[self.type.lower()].custom())
        return c

    def property(self, propName):
        if propName == None:
            return None
        if propName in self.properties:
            return self.properties[propName]
        elif self.type.lower() in self.module.catalog:
            return self.module.catalog[self.type.lower()].property(propName)
        else:
            return None

    def positional(self):
        c= [self.properties[v] for v in self.properties if self.properties[v].positional]
        if self.type.lower() in self.module.catalog:
            c = c+self.module.catalog[self.type.lower()].positional()
        return c

    def all(self):
        c= [v for v in self.properties]
        if self.type.lower() in self.module.catalog:
            c = c+self.module.catalog[self.type.lower()].all()
        return c


class Property:
    def __init__(self,name:str,t:Type,dict):
        self.name=name
        self.type=t;
        self.alias=None
        self.positional="(meta.positional)" in dict
        self.custom = "(meta.custom)" in dict
        if "(meta.alias)" in dict:
            self.alias=dict["(meta.alias)"]
        if isinstance(dict, str):
            self.propRange = dict
        elif "type" in dict:
            self.propRange = dict["type"]
        else:
            self.propRange = "string"
        pass

loaded={}

def load(name: str)  -> Module:
    if name in loaded:
        return loaded[name]
    pth = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(pth,"schemas", name+".raml"), "r") as f:
        cfg = yaml.load(f);
    loaded[name]=Module(cfg);
    return loaded[name]

def parse(name:str,p):
    m=load(name)
    if type(p)==str:
        with open(p, "r") as f:
            return m.instantiate(yaml.load(f));
    return m.instantiate(p);