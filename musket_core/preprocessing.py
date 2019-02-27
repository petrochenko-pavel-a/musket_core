import functools
import importlib
import inspect

class PreprocessedDataSet:

    def __init__(self,parent,func,**kwargs):
        self.parent=parent
        self.func=func
        self.kw=kwargs
        pass

    def __getitem__(self, item):
        pi=self.parent[item]
        pi.x=self.func(pi.x,**self.kw)
        return pi

    def __len__(self):
        return len(self.parent)

def dataset_preprocessor(func):
    def wrapper(input,**kwargs):
        return PreprocessedDataSet(input,func,**kwargs)
    wrapper.args=inspect.signature(func).parameters
    return wrapper