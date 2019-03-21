from musket_core.utils import save_yaml,load_yaml,ensure,delete_file,load_string,save_string
import os
import numpy as np
import random
import typing
from  musket_core.parralel import Task,Error
from musket_core import generic
from musket_core.structure_constants import constructPredictionsDirPath, constructSummaryYamlPath, constructInProgressYamlPath, constructConfigYamlPath, constructErrorYamlPath, constructConfigYamlConcretePath

class Experiment:

    def __init__(self,path,allowResume = False,project=None):
        self.path=path
        self._cfg=None
        self.project=project
        self.allowResume = allowResume
        self.gpus=1
        self.onlyReports = False
        self.launchTasks = True

    def cleanup(self):
        if os.path.exists(self.getPredictionsDirPath()):
            for pr in os.listdir(self.getPredictionsDirPath()):
                os.remove(f"{self.getPredictionsDirPath()}/{pr}")
        if os.path.exists(self.getSummaryYamlPath()):
            os.remove(self.getSummaryYamlPath())

    def metrics(self):
        if os.path.exists(self.getSummaryYamlPath()):
            return load_yaml(self.getSummaryYamlPath())
        return {}


    def name(self):
        if self.project is not None:
            return self.path[len(self.project.experimentsPath())+1:].replace("\\","/")
        return os.path.basename(self.path)


    def hyperparameters(self):
        config = self.config()
        ps= config["hyperparameters"] if "hyperparameters" in config else None
        return ps

    def generateMetrics(self):
        cfg = self.parse_config()
        cfg.generateReports()

    def parse_config(self):
        if os.path.exists(self.getConfigYamlPath()):
            cfg = generic.parse(self.getConfigYamlPath())

        else:
            cfg = generic.parse(self.getConfigYamlConcretePath())
        if self.allowResume:
            cfg.setAllowResume(self.allowResume)
        return cfg

    def log_path(self,fold,stage):
        return os.path.join(self.path,"metrics","metrics-"+str(fold)+"."+str(stage)+".csv")

    def report(self):
        cf=self.parse_config()
        path = os.path.join(os.path.dirname(__file__),"templates","logs.html")
        template=load_string(path)
        eex=self.apply()
        for e in eex:
            for i in range(cf.folds_count):
                for j in range(len(cf.stages)):
                    if os.path.exists(e.log_path(i,j)):
                        m=load_string(e.log_path(i,j))
                        ensure(os.path.join(e.path,"reports"))
                        rp=os.path.join(e.path, "reports", "report-" + str(i) + "." + str(j) + ".html")
                        save_string(rp,template.replace("${metrics}",m))


    def result(self,forseRecalc=False):
        pi = self.apply(True)
        if forseRecalc:
            self.cleanup()
        m=self.metrics()
        if m is None:
            return None
        if self.hyperparameters() is not None:

            return
        if len(pi) > 1:
            vals = []
            for i in pi:
                if i.isCompleted() or True:
                    if forseRecalc:
                        i.cleanup()
                    i.generateMetrics()
                    m = i.metrics()
                    pm = i.config()["primary_metric"]
                    if "val_" in pm:
                        pm = pm[4:]
                    mv = m["allStages"][pm + "_holdout"]
                    if "aggregation_metric" in i.config():
                        mv = m["allStages"][i.config()["aggregation_metric"]]
                    vals.append(mv)
            m = np.mean(vals)
            save_yaml(self.getSummaryYamlPath(),
                      {"mean": float(m), "max": float(np.max(vals)), "min": float(np.min(vals)),
                       "std": float(np.std(vals))})
            return float(m)
        else:
            m = self.metrics()
            if isinstance(m,dict):
                pm = self.config()["primary_metric"]
                if "val_" in pm:
                    pm = pm[4:]
                mv = m["allStages"][pm + "_holdout"]
                if "aggregation_metric" in self.config():
                    mv = m["allStages"][self.config()["aggregation_metric"]]
                return mv
            if isinstance(m,float):
                return m
            if isinstance(m,int):
                return m
            return 1000000
        pass

    def isCompleted(self):
        return os.path.exists(self.getSummaryYamlPath())

    def isInProgress(self):
        return os.path.exists(self.getInProgressYamlPath())

    def setInProgress(self, val:bool):
        if val and not self.isInProgress():
            save_yaml(self.getInProgressYamlPath(), True)
        elif not val and self.isInProgress():
            delete_file(self.getInProgressYamlPath())

    def config(self):
        if self._cfg is not None:
            return self._cfg
        if os.path.exists(self.getConfigYamlPath()):
            self._cfg= load_yaml(self.getConfigYamlPath())

        else:
            self._cfg=load_yaml(self.getConfigYamlConcretePath())
        return self._cfg

    def dumpTo(self,path,extra,remove=()):
        c=self.config().copy()
        for k in extra:
            c[k]=extra[k]
        for r in remove:
            del c[r]
        return save_yaml(constructConfigYamlConcretePath(path),c)

    def fit(self,reporter=None)->typing.Collection[Task]:
        subExps=self.apply(True)
        try:
            if len(subExps)>1:
                all_units_of_work=[]
                for x in subExps:
                    m=x.config()
                    if "num_seeds" in m:
                        del m["num_seeds"]
                    if reporter is not None and reporter.isCanceled():
                        save_yaml(self.getSummaryYamlPath(), "Cancelled")
                        return []
                    for i in x.fit(reporter):
                        all_units_of_work.append(i)
                if reporter is not None and reporter.isCanceled():
                    save_yaml(self.getSummaryYamlPath(), "Cancelled")
                    return []
                def c():
                    self.result()
                t=Task(c)
                t.deps=all_units_of_work.copy()
                all_units_of_work.append(t)
                return all_units_of_work

            if not self.onlyReports:
                self.cleanup()
            self.setInProgress(True)
            cfg = self.parse_config()
            cfg.gpus=self.gpus
            cfg._reporter=reporter
            units_of_work=[]
            if self.onlyReports:
                units_of_work.append(Task(lambda :cfg.generateReports()))
            else:
                units_of_work=units_of_work+cfg.fit(parallel=True)

            r=Task(lambda: self.result())
            r.deps=units_of_work.copy()
            units_of_work.append(r)

            r = Task(lambda ts: self.onExperimentFinished(ts), runOnErrors=True, needs_tasks=True)
            r.deps = units_of_work.copy()
            units_of_work.append(r)
            return units_of_work
        except:
            self.onExperimentFinished()
            self._onErrors([Error()])


    def _onErrors(self, errors):
        save_yaml(self.getErrorYamlPath(), {"errors":[x.log() for x in errors]})
        save_yaml(self.getSummaryYamlPath(), "Error")

    def onExperimentFinished(self,tasksState:Task=None):
        if tasksState is not None:
            errors=tasksState.all_errors()
            if len(errors)>0:
                self._onErrors(errors)
            else:
                if os.path.exists(self.getErrorYamlPath()):
                    os.remove(self.getErrorYamlPath())
        self.setInProgress(False)

    def apply(self,all=False):
        if self.hyperparameters() is not None:
            return [self]
        m=self.config()
        if "num_seeds" in m:
            paths = []
            for i in range(m["num_seeds"]):
                i_ = self.path + "/" + str(i)
                ensure(i_)
                if not all:
                    if Experiment(i_).isCompleted():
                        continue

                s=random.randint(0,100000)
                if not all or not os.path.exists(constructConfigYamlConcretePath(i_)):
                    self.dumpTo(i_, {"testSplitSeed":s},["num_seeds"])
                e=Experiment(i_, self.allowResume)
                e.gpus=self.gpus
                e.onlyReports=self.onlyReports
                e.launchTasks=self.launchTasks
                e.project=self.project
                paths.append(e)
            return paths
        return [self]

    def getSummaryYamlPath(self):
        return constructSummaryYamlPath(self.path)

    def getInProgressYamlPath(self):
        return constructInProgressYamlPath(self.path)

    def getConfigYamlPath(self):
        return constructConfigYamlPath(self.path)

    def getConfigYamlConcretePath(self):
        return constructConfigYamlConcretePath(self.path)

    def getErrorYamlPath(self):
        return constructErrorYamlPath(self.path)

    def getPredictionsDirPath(self):
        return constructPredictionsDirPath(self.path)
