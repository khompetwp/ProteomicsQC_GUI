"""Measure key widgets at supported Tk font scaling without changing Windows settings."""
from pathlib import Path
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r'''
import sys, json, tkinter as tk
sys.path.insert(0, sys.argv[1])
from proteomicsqc.gui import MSQCApp
original=tk.Tk.__init__
def initialize(self,*a,**kw):
    original(self,*a,**kw)
    self.tk.call('tk','scaling',float(sys.argv[2]))
tk.Tk.__init__=initialize
app=MSQCApp()
app.geometry(sys.argv[3])
app.update()
width,height=app.winfo_width(),app.winfo_height()
bad=[]
for name in ['source_box','level_box','input_entry','run_btn','cancel_btn','multiqc_check','tabs']:
    w=getattr(app,name)
    x,y=w.winfo_rootx()-app.winfo_rootx(),w.winfo_rooty()-app.winfo_rooty()
    if x<0 or y<0 or x+w.winfo_width()>width+2 or y+w.winfo_height()>height+2:
        bad.append(name)
result={'scaling':sys.argv[2],'size':[width,height],'clipped_controls':bad}
app.destroy()
print(json.dumps(result))
assert not bad,result
'''


def main():
    folder=ROOT/'build'/'layout_validation'
    folder.mkdir(parents=True,exist_ok=True)
    records=[]
    for scale in (1.3333,1.6667,2.0):
        for geometry in ('1180x820','860x650'):
            result=subprocess.run([sys.executable,'-X','utf8','-c',SCRIPT,str(ROOT),str(scale),geometry],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60,env={**os.environ,'PROTEOMICSQC_SETTINGS':str(folder/'settings.json')})
            assert result.returncode==0,(result.stdout,result.stderr)
            records.append(json.loads(result.stdout.strip().splitlines()[-1]))
    (folder/'verification.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print(json.dumps(records,indent=2))


if __name__=='__main__':
    main()
