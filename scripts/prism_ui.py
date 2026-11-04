"""Windows-native Prism bridge; usable as a library, CLI, or MCP backend."""
from __future__ import annotations
import argparse,ctypes as c,json,os,re,time
from ctypes import wintypes as w
from pathlib import Path

def native_user32():
 u=c.WinDLL('user32',use_last_error=True)
 for name,args,ret in [
  ('GetWindowTextW',[w.HWND,w.LPWSTR,c.c_int],c.c_int),('GetClassNameW',[w.HWND,w.LPWSTR,c.c_int],c.c_int),
  ('GetWindowThreadProcessId',[w.HWND,c.POINTER(w.DWORD)],w.DWORD),
  ('IsWindow',[w.HWND],w.BOOL),('IsWindowVisible',[w.HWND],w.BOOL),('IsWindowEnabled',[w.HWND],w.BOOL),
  ('IsIconic',[w.HWND],w.BOOL),('IsChild',[w.HWND,w.HWND],w.BOOL),('GetDlgCtrlID',[w.HWND],c.c_int),
  ('ShowWindow',[w.HWND,c.c_int],w.BOOL),('BringWindowToTop',[w.HWND],w.BOOL),
  ('AttachThreadInput',[w.DWORD,w.DWORD,w.BOOL],w.BOOL),('SetThreadDpiAwarenessContext',[c.c_void_p],c.c_void_p)]:
  f=getattr(u,name);f.argtypes=args;f.restype=ret
 return u

class PrismBridge:
 def __init__(self,project_hint=None,frame_hwnd=None):
  if os.name!='nt':raise RuntimeError('Prism UI bridge requires an interactive Windows desktop.')
  self.u=native_user32();self.k=c.WinDLL('kernel32',use_last_error=True);u=self.u
  for name,args,ret in [('GetAncestor',[w.HWND,w.UINT],w.HWND),('GetParent',[w.HWND],w.HWND),('GetWindow',[w.HWND,w.UINT],w.HWND),('GetForegroundWindow',[],w.HWND),('GetMenu',[w.HWND],w.HMENU),('WindowFromPoint',[w.POINT],w.HWND),('SetForegroundWindow',[w.HWND],w.BOOL),('GetWindowThreadProcessId',[w.HWND,c.POINTER(w.DWORD)],w.DWORD),('GetWindowRect',[w.HWND,c.POINTER(w.RECT)],w.BOOL),('SendMessageTimeoutW',[w.HWND,w.UINT,w.WPARAM,w.LPARAM,w.UINT,w.UINT,c.POINTER(c.c_size_t)],w.LPARAM)]:
   f=getattr(u,name);f.argtypes=args;f.restype=ret
  self.dpi();frames=self.windows()
  candidates=[x for x in frames if (x['hwnd']==frame_hwnd if frame_hwnd else not project_hint or project_hint in x['title'])]
  if len(candidates)!=1:raise RuntimeError(f'Choose one project by a unique title substring or frame HWND. Candidates: {frames}')
  self.frame=candidates[0]['hwnd'];self.pid=self.pid_of(self.frame);self.project_hint=project_hint;self.initial_title=candidates[0]['title']
  self._script_dialogs={}
 def dpi(self):self.u.SetThreadDpiAwarenessContext(c.c_void_p(-4))
 def pid_of(self,h):
  p=w.DWORD();self.u.GetWindowThreadProcessId(h,c.byref(p));return p.value
 def text(self,h):
  b=c.create_unicode_buffer(4096);self.u.GetWindowTextW(h,b,len(b));return b.value
 def cls(self,h):
  b=c.create_unicode_buffer(256);self.u.GetClassNameW(h,b,len(b));return b.value
 def send(self,h,msg,wp=0,lp=0):
  out=c.c_size_t();ok=self.u.SendMessageTimeoutW(h,msg,wp,lp,3,5000,c.byref(out))
  if not ok:raise RuntimeError(f'Prism UI message timed out/failed: HWND {h}, message {msg:#x}; inspect window state.')
  return c.c_ssize_t(out.value).value
 def windows(self):
  out=[];callback=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
  @callback
  def visit(h,_):
   if self.cls(h).startswith('IPMainClass') and 'GraphPad Prism' in self.text(h):out.append({'hwnd':int(h),'title':self.text(h),'pid':self.pid_of(h)})
   return True
  self.u.EnumWindows(visit,0);return out
 @classmethod
 def discover(cls):
  if os.name!='nt':return []
  obj=cls.__new__(cls);obj.u=native_user32();return obj.windows()
 def validate(self):
  if not self.u.IsWindow(self.frame) or self.pid_of(self.frame)!=self.pid or not self.cls(self.frame).startswith('IPMainClass'):raise RuntimeError('Session window was closed/reused; reconnect explicitly.')
  current=self.text(self.frame)
  if current!=self.initial_title:
   def identity(title):
    match=re.match(r'^(.*?\.(?:prism|pzf|pzfx))(?::|\s+-|$)',title,re.I);return match.group(1) if match else title.split(':',1)[0]
   oldfile=identity(self.initial_title);newfile=identity(current)
   if oldfile!=newfile:raise RuntimeError(f'Project changed from {oldfile} to {newfile}; reconnect to the intended working copy.')
  return current
 def belongs(self,h):
  if not self.u.IsWindow(h) or self.pid_of(h)!=self.pid:return False
  root=self.u.GetAncestor(h,2) or h
  if root in getattr(self,'_script_dialogs',{}) and self._script_dialog_matches(root,self._script_dialogs[root]):return True
  if root==self.frame or self.u.IsChild(self.frame,h):return True
  seen=set()
  while root and root not in seen:
   if root==self.frame:return True
   seen.add(root);root=self.u.GetWindow(root,4)
  return len(self.windows())==1 and not self.cls(h).startswith('IPMainClass')
 def _script_dialog_matches(self,h,path):
  if not self.u.IsWindow(h) or not self.u.IsWindowVisible(h) or self.pid_of(h)!=self.pid or self.cls(h)!='#32770':return False
  if not re.search(r'脚本|script|出错!已停止!|error.*stopped',self.text(h),re.I):return False
  owner=self.u.GetWindow(h,4)
  if owner and owner!=self.frame:return False
  labels=[];callback=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
  @callback
  def visit(ch,_):
   if self.u.GetDlgCtrlID(ch)==1911 and self.cls(ch)=='Static':labels.append(self.text(ch))
   return True
  self.u.EnumChildWindows(h,visit,0)
  if len(labels)!=1:return False
  label=re.fullmatch(r'\s*(?:文件|file)\s*:\s*(.*?)\s*',labels[0],re.I)
  return bool(label and label.group(1).casefold()==str(path).casefold())
 def _script_windows(self):
  result=[];callback=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
  @callback
  def visit(h,_):
   if self.pid_of(h)==self.pid and self.u.IsWindowVisible(h) and self.cls(h)=='#32770' and re.search(r'脚本|script|出错!已停止!|error.*stopped',self.text(h),re.I):result.append(int(h))
   return True
  self.u.EnumWindows(visit,0);return result
 def guard(self,h):
  self.validate()
  if not self.belongs(h):raise RuntimeError('Control/window does not belong to the connected project; rediscover controls.')
 def focus(self,h=None):
  self.validate();h=h or self.frame;self.guard(h);root=self.u.GetAncestor(h,2) or h
  if self.u.IsIconic(root):self.u.ShowWindow(root,9)
  caller=self.k.GetCurrentThreadId();attached=[]
  for item in [self.u.GetForegroundWindow(),root]:
   thread=self.u.GetWindowThreadProcessId(item,None)
   if thread and thread!=caller and thread not in attached:self.u.AttachThreadInput(caller,thread,True);attached.append(thread)
  try:self.u.BringWindowToTop(root);self.u.SetForegroundWindow(root)
  finally:
   for thread in attached:self.u.AttachThreadInput(caller,thread,False)
  if self.u.GetForegroundWindow()!=root:
   self.u.keybd_event(0x12,0,0,0);self.u.keybd_event(0x12,0,2,0);self.u.SetForegroundWindow(root)
  time.sleep(.2);self.dpi()
  if self.u.GetForegroundWindow()!=root:raise RuntimeError('Could not focus the intended Prism window; inspect desktop/modal state.')
 def rect(self,h):
  self.dpi();r=w.RECT()
  if not self.u.GetWindowRect(h,c.byref(r)):raise RuntimeError('Cannot read window rectangle; rediscover target.')
  if self.u.GetAncestor(h,2)==h:
   # Maximized GetWindowRect includes invisible resize borders outside monitors.
   # Use the visible DWM frame for both screenshots and relative click coordinates.
   d=c.WinDLL('dwmapi');d.DwmGetWindowAttribute.argtypes=[w.HWND,w.DWORD,c.c_void_p,w.DWORD];visible=w.RECT()
   if d.DwmGetWindowAttribute(h,9,c.byref(visible),c.sizeof(visible))==0 and visible.right>visible.left:r=visible
  return [r.left,r.top,r.right,r.bottom]
 def controls(self,h=None):
  h=h or self.frame;self.guard(h);self.dpi();out=[];callback=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
  @callback
  def visit(ch,_):
   if self.u.IsWindowVisible(ch):out.append({'hwnd':int(ch),'id':self.u.GetDlgCtrlID(ch),'class':self.cls(ch),'text':self.read(ch),'rect':self.rect(ch),'enabled':bool(self.u.IsWindowEnabled(ch))})
   return True
  self.u.EnumChildWindows(h,visit,0);return out
 def read(self,h):
  self.guard(h);b=c.create_unicode_buffer(4096);self.send(h,0xD,len(b),c.addressof(b));return b.value
 def dialogs(self):
  out=[];callback=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
  @callback
  def visit(ch,_):
   if ch!=self.frame and self.u.IsWindowVisible(ch) and self.belongs(ch) and self.cls(ch)=='#32770':out.append({'hwnd':int(ch),'title':self.text(ch),'controls':self.controls(ch)})
   return True
  self.u.EnumWindows(visit,0);return out
 def wait_dialog(self,title,timeout=10):
  deadline=time.monotonic()+min(timeout,55)
  while time.monotonic()<deadline:
   found=[d for d in self.dialogs() if title in d['title']]
   if len(found)==1:return found[0]
   if len(found)>1:raise RuntimeError(f'Ambiguous dialog title {title!r}; inspect dialogs and use an explicit HWND.')
   time.sleep(.15)
  raise RuntimeError(f'Dialog {title!r} did not appear. Current state: {self.dialogs()}')
 def control(self,dialog,ident,cls=None):
  found=[x for x in self.controls(dialog) if x['id']==ident and (not cls or x['class']==cls)]
  if len(found)!=1:raise RuntimeError(f'Expected one control ID {ident}, class {cls}; got {found}. Inspect nested dialogs.')
  return found[0]['hwnd']
 def find_menu(self,pattern):
  self.focus();u=self.u;u.GetSubMenu.argtypes=[w.HMENU,c.c_int];u.GetSubMenu.restype=w.HMENU;u.GetMenuItemID.argtypes=[w.HMENU,c.c_int];u.GetMenuItemID.restype=w.UINT;u.GetMenuItemCount.argtypes=[w.HMENU];u.GetMenuStringW.argtypes=[w.HMENU,w.UINT,w.LPWSTR,c.c_int,w.UINT];menu=u.GetMenu(self.frame)
  if not menu:return []
  self.send(self.frame,0x116,menu);found=[]
  def walk(m,prefix):
   for i in range(u.GetMenuItemCount(m)):
    b=c.create_unicode_buffer(1024);u.GetMenuStringW(m,i,b,len(b),0x400);sm=u.GetSubMenu(m,i);path=prefix+[b.value]
    if sm:self.send(self.frame,0x117,sm,i);walk(sm,path)
    elif re.search(pattern,b.value,re.I):found.append({'id':u.GetMenuItemID(m,i),'text':b.value,'path':path})
  walk(menu,[]);return found
 def button(self,h,expect_closed=None):
  self.guard(h)
  if self.cls(h)!='Button':raise ValueError('Use button only with a discovered native Button control.')
  self.focus(h);self.send(h,0xF5);time.sleep(.25)
  if expect_closed:
   deadline=time.monotonic()+8
   while self.u.IsWindow(expect_closed) and self.u.IsWindowVisible(expect_closed) and time.monotonic()<deadline:time.sleep(.15)
   if self.u.IsWindow(expect_closed) and self.u.IsWindowVisible(expect_closed):raise RuntimeError(f'Dialog did not close; inspect current prompts: {self.dialogs()}')
  return {'clicked':h,'dialogs':[{'hwnd':d['hwnd'],'title':d['title']} for d in self.dialogs()]}
 def click(self,h,x,y,double=False):
  self.guard(h);self.focus(h);left,top,right,bottom=self.rect(h)
  if not (0<=x<right-left and 0<=y<bottom-top):raise ValueError('Click is outside the captured target window.')
  self.u.SetCursorPos(left+x,top+y);time.sleep(.1);hit=self.u.WindowFromPoint(w.POINT(left+x,top+y))
  if not self.belongs(hit):raise RuntimeError('Target is covered by a different application; do not click through it.')
  for _ in range(2 if double else 1):self.u.mouse_event(2,0,0,0,0);self.u.mouse_event(4,0,0,0,0);time.sleep(.12)
  time.sleep(.25);return {'clicked_window':h,'x':x,'y':y}
 def edit(self,h,value):
  self.guard(h)
  if self.cls(h)!='Edit':raise ValueError('Edit requires an actual Edit child; inspect combo children first.')
  self.focus(h);r=self.rect(h);self.click(h,(r[2]-r[0])//2,(r[3]-r[1])//2)
  b=c.create_unicode_buffer(str(value));self.send(h,0xB1,0,-1);self.send(h,0xC2,1,c.addressof(b));self.u.keybd_event(9,0,0,0);self.u.keybd_event(9,0,2,0);time.sleep(.2)
  return {'hwnd':h,'value':self.read(h),'requested':str(value),'reopen_dialog_to_verify_commit':True}
 def combo(self,h):
  self.guard(h)
  if self.cls(h)!='ComboBox':raise ValueError('Expected ComboBox.')
  count=self.send(h,0x146);items=[]
  if count>10000:raise RuntimeError('Unexpected combo size; rediscover target.')
  for i in range(count):
   length=self.send(h,0x149,i)
   if not 0<=length<8192:raise RuntimeError('Unexpected combo item length; rediscover target.')
   b=c.create_unicode_buffer(length+1);self.send(h,0x148,i,c.addressof(b));items.append(b.value)
  return {'hwnd':h,'items':items,'selected':self.send(h,0x147),'value':self.read(h)}
 def combo_set(self,h,text=None,index=None):
  data=self.combo(h)
  if text is not None:
   if data['items'].count(text)!=1:raise ValueError(f'Combo text must match one actual item. Items: {data["items"]}')
   index=data['items'].index(text)
  if index is None or not 0<=index<len(data['items']):raise ValueError('Combo index out of range.')
  self.send(h,0x14E,index);self.send(self.u.GetParent(h),0x111,(1<<16)|(self.u.GetDlgCtrlID(h)&0xffff),h);time.sleep(.15);return self.combo(h)
 def check(self,h,state):
  self.guard(h);current=self.send(h,0xF0)
  if current!=state:self.button(h)
  result=self.send(h,0xF0)
  if result!=state:raise RuntimeError('Checkbox state did not commit; inspect dialog.')
  return {'hwnd':h,'checked':result}
 def tab(self,h,index):
  self.guard(h)
  if self.cls(h)!='SysTabControl32' or not 0<=index<self.send(h,0x1304):raise ValueError('Invalid tab control/index.')
  self.send(h,0x1330,index);time.sleep(.15);return {'selected_index':self.send(h,0x130B),'controls':self.controls(self.u.GetParent(h))}
 def capture(self,path,h=None,focus=True):
  from PIL import ImageGrab
  h=h or self.frame;self.guard(h)
  if focus:self.focus(h)
  self.dpi();r=self.rect(h)
  if not self.u.IsWindowVisible(h) or r[2]<=r[0] or r[3]<=r[1]:raise RuntimeError('Window vanished/minimized; rediscover before capturing.')
  for x,y in [((r[0]+r[2])//2,(r[1]+r[3])//2),(r[0]+5,r[1]+5),(r[2]-5,r[1]+5),(r[0]+5,r[3]-5),(r[2]-5,r[3]-5)]:
   hit=self.u.WindowFromPoint(w.POINT(x,y))
   if not self.belongs(hit):raise RuntimeError('Screenshot would include an occluding application; clear overlap first.')
  p=Path(path).resolve();p.parent.mkdir(parents=True,exist_ok=True);ImageGrab.grab(bbox=tuple(r),all_screens=True).save(p);return {'path':str(p),'window_rect':r}
 def run_script(self,path):
  path=Path(path).resolve();data=path.read_bytes()
  if not data.startswith(b'\xef\xbb\xbf') or not data.endswith(b'\n'):raise ValueError('Write .pzc as UTF-8 BOM with a final newline before execution.')
  if not path.is_file():raise FileNotFoundError(path)
  self.focus();open_dialogs=[d for d in self.dialogs() if re.search(r'打开脚本|open.*script',d['title'],re.I) and any(x['class']=='Edit' and x['id']==1148 for x in d['controls'])]
  if not open_dialogs:
   choices=self.find_menu(r'打开脚本|open.*script')
   if len(choices)!=1:raise RuntimeError(f'Cannot uniquely discover Open Script menu for this Prism/UI language: {choices}. Inspect the current menu/UI; no version-specific ID is assumed.')
   self.send(self.frame,0x111,choices[0]['id'])
  def wait_script_dialog(file_open=False):
   deadline=time.monotonic()+10
   while time.monotonic()<deadline:
    choices=[d for d in self.dialogs() if re.search(r'脚本|script',d['title'],re.I) and (not file_open or any(x['class']=='Edit' and x['id']==1148 for x in d['controls']))]
    if not file_open:choices=[d for d in choices if any(x['class']=='Button' and x['enabled'] and re.fullmatch(r'\s*(?:运行|run)\s*(?:\([^)]*\))?\s*',x['text'],re.I) for x in d['controls'])]
    if len(choices)==1:return choices[0]
    if len(choices)>1:raise RuntimeError('Multiple script dialogs: inspect state explicitly.')
    time.sleep(.15)
   raise RuntimeError('Script dialog did not appear for this UI language/version; use current UI discovery or GUI fallback.')
  dialog=wait_script_dialog(True);edit=self.control(dialog['hwnd'],1148,'Edit');buf=c.create_unicode_buffer(str(path));self.send(edit,0xC,0,c.addressof(buf))
  existing=set(self._script_windows())
  self.button(self.control(dialog['hwnd'],1,'Button'))
  # Some Prism builds create the editor as an ownerless top-level window.
  # Adopt only a new, unique editor displaying the exact just-opened script path.
  deadline=time.monotonic()+5;candidates=[]
  while time.monotonic()<deadline:
   candidates=[h for h in self._script_windows() if h not in existing and self._script_dialog_matches(h,path)]
   if candidates:break
   time.sleep(.1)
  if len(candidates)==1:self._script_dialogs[candidates[0]]=path
  elif len(candidates)>1:raise RuntimeError('Multiple matching new script dialogs; refusing to choose one.')
  script=wait_script_dialog(False);run=[x for x in script['controls'] if x['class']=='Button' and x['enabled'] and re.fullmatch(r'\s*(?:运行|run)\s*(?:\([^)]*\))?\s*',x['text'],re.I)]
  if len(run)!=1:raise RuntimeError('Cannot uniquely identify Run button; inspect current script dialog.')
  # Prism may decode a UTF-8 BOM as local-codepage characters after Save As.
  # Compare the displayed script to the authorized source before any command runs.
  editors=[x for x in script['controls'] if x['class']=='Edit' and x['id']==1914]
  if len(editors)!=1:raise RuntimeError('Cannot inspect the loaded script editor; refusing to run unverified commands.')
  expected=data.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
  displayed=self.read(editors[0]['hwnd']).lstrip('\ufeff').replace('\r\n','\n').replace('\r','\n')
  corrected=displayed!=expected
  if corrected:
   self.edit(editors[0]['hwnd'],expected.replace('\n','\r\n'))
   actual=self.read(editors[0]['hwnd']).lstrip('\ufeff').replace('\r\n','\n').replace('\r','\n')
   if actual!=expected:raise RuntimeError('Loaded script text differs from the requested script after correction; no commands were run.')
  log=path.with_suffix('.log');previous=log.stat().st_mtime_ns if log.exists() else None;self.button(run[0]['hwnd']);deadline=time.monotonic()+50;status='pending';txt=None
  while time.monotonic()<deadline:
   if log.exists() and log.stat().st_mtime_ns!=previous:
    raw=log.read_bytes();txt=None
    for encoding in ('utf-8-sig','utf-16','gb18030'):
     try:txt=raw.decode(encoding);break
     except UnicodeError:pass
    txt=txt or raw.decode('utf8',errors='replace')
    if '发生问题' in txt or '已停止' in txt or '由于出错' in txt:status='error';break
    if '完成!' in txt or 'Completed' in txt or 'Finished' in txt:status='completed';break
   if not self.u.IsWindow(script['hwnd']):status='closed';break
   time.sleep(.2)
  # Save As can legitimately rename this same frame. Update only after this submitted script.
  self.initial_title=self.text(self.frame)
  result={'status':status,'log':str(log),'log_text':txt if log.exists() else None,'script_dialog_adopted':bool(candidates),'script_text_corrected':corrected,'dialogs':[{'hwnd':d['hwnd'],'title':d['title']} for d in self.dialogs()]}
  if status!='completed':
   # Only a confirmed failed script may be dismissed, and only when its
   # exact path and freshly adopted window still match. Never close unknown UI.
   if status=='error' and script['hwnd'] in self._script_dialogs and self._script_dialog_matches(script['hwnd'],path):
    try:
     close=self.control(script['hwnd'],2,'Button');self.button(close,script['hwnd']);result['owned_error_dialog_closed']=True;result['dialogs']=[{'hwnd':d['hwnd'],'title':d['title']} for d in self.dialogs()]
    except Exception as e:result['owned_error_dialog_closed']=False;result['cleanup_error']=str(e)
   raise RuntimeError(json.dumps({**result,'warning':'No verified completion log. Inspect the live project and log before retrying.'},ensure_ascii=False))
  self._script_dialogs.clear()
  self.focus();return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--project');p.add_argument('--frame-hwnd',type=int);s=p.add_subparsers(dest='command',required=True)
 s.add_parser('windows');s.add_parser('dialogs');s.add_parser('focus')
 for name in ['controls','read','combo','button','check','edit','tab','combo-set','click','capture','run-script']:
  q=s.add_parser(name)
  if name not in ('capture','run-script'):q.add_argument('--hwnd',type=int,required=name!='controls')
  if name=='button':q.add_argument('--expect-closed',type=int)
  if name=='check':q.add_argument('--state',type=int,choices=[0,1],required=True)
  if name=='edit':q.add_argument('--value',required=True)
  if name=='tab':q.add_argument('--index',type=int,required=True)
  if name=='combo-set':q.add_argument('--index',type=int);q.add_argument('--text')
  if name=='click':q.add_argument('--x',type=int,required=True);q.add_argument('--y',type=int,required=True);q.add_argument('--double',action='store_true')
  if name=='capture':q.add_argument('--hwnd',type=int);q.add_argument('--output',required=True)
  if name=='run-script':q.add_argument('--script',required=True)
 x=p.parse_args()
 if x.command=='windows':result=PrismBridge.discover()
 else:
  if not x.project and not x.frame_hwnd:raise ValueError('Explicit --project or --frame-hwnd is required for targeted operations.')
  b=PrismBridge(x.project,x.frame_hwnd)
  if x.command=='dialogs':result=b.dialogs()
  elif x.command=='controls':result=b.controls(x.hwnd)
  elif x.command=='focus':b.focus();result={'title':b.text(b.frame)}
  elif x.command=='read':result={'value':b.read(x.hwnd)}
  elif x.command=='combo':result=b.combo(x.hwnd)
  elif x.command=='combo-set':result=b.combo_set(x.hwnd,x.text,x.index)
  elif x.command=='button':result=b.button(x.hwnd,x.expect_closed)
  elif x.command=='check':result=b.check(x.hwnd,x.state)
  elif x.command=='edit':result=b.edit(x.hwnd,x.value)
  elif x.command=='tab':result=b.tab(x.hwnd,x.index)
  elif x.command=='click':result=b.click(x.hwnd,x.x,x.y,x.double)
  elif x.command=='capture':result=b.capture(x.output,x.hwnd)
  else:result=b.run_script(x.script)
 print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
