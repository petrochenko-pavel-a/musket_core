from musket_core import parralel
from musket_core import hyper
class ProgressMonitor:

    def isCanceled(self)->bool:
        return False

    def task(self,message:str,totalWork:int):
        return False

    def worked(self,numWorked)->bool:
        return False

    def error(self,message:str):
        pass

    def stdout(self,message):
        pass

    def stderr(self,message):
        pass

    def done(self):
        return False

import yaml

class Launch(yaml.YAMLObject):
    yaml_tag = u'!com.onpositive.dside.ui.LaunchConfiguration'

    def __init__(self,gpusPerNet,numGpus,numWorkers,experiments,allowResume=False,onlyReports:bool=False,launchTasks:bool=False):
        self.gpusPerNet=gpusPerNet
        self.numGpus=numGpus
        self.numWorkers=numWorkers
        self.experiments=experiments
        self.allowResume=allowResume
        self.onlyReports=onlyReports
        self.launchTasks=launchTasks
        pass

    def perform(self,server,reporter:ProgressMonitor):
        workPerProject={}
        for e in self.experiments:
            inde=e.index("experiments")
            pp=e[0:inde]
            localPath=e
            if pp in workPerProject:
                workPerProject[pp].append(localPath)
            else:
                workPerProject[pp]=[localPath]
        executor = parralel.get_executor(self.numWorkers, self.numGpus)

        for projectPath in workPerProject:
            project=server.project(projectPath)
            experiments=[project.byFullPath(e) for e in workPerProject[projectPath]]
            reporter.task("Launching:" + str(len(experiments)), len(experiments))
            allTasks=[]
            for exp in experiments:

                exp.allowResume=self.allowResume
                exp.gpus=self.gpusPerNet
                exp.onlyReports=self.onlyReports
                exp.launchTasks=self.launchTasks
                if exp.hyperparameters() is not None:
                    hyper.optimize(exp,executor,reporter)

                else:
                    try:
                        allTasks=allTasks+exp.fit(reporter)
                    except:
                        pass
                    if len(allTasks)>self.numWorkers:
                        executor.execute(allTasks)
                        allTasks=[]
            executor.execute(allTasks)
        reporter.done()