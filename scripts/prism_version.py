"""Conservative Prism version detection and version/format-specific workflow routing."""
from __future__ import annotations
import ctypes
import os
import re
from ctypes import wintypes


def parse_title(title):
    """Parse the application part of a Prism title, never a project filename."""
    text=str(title).rsplit(' - ',1)[-1].strip()
    m=re.search(r'\b(?:GraphPad\s+)?Prism\s*(?:v(?:ersion)?\.?\s*)?(\d{1,2})(?:\.(\d{1,3}))?(?:\.(\d{1,3}))?',text,re.IGNORECASE)
    if not m:return None
    return tuple(int(x) if x is not None else None for x in m.groups())


def process_image(pid):
    """Best-effort full executable path of an existing process, without launching it."""
    if os.name!='nt':return None
    try:
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
        k.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)];k.QueryFullProcessImageNameW.restype=wintypes.BOOL
        k.CloseHandle.argtypes=[wintypes.HANDLE];k.CloseHandle.restype=wintypes.BOOL
        h=k.OpenProcess(0x1000,False,int(pid))
        if not h:return None
        try:
            buf=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(buf))
            if not k.QueryFullProcessImageNameW(h,0,buf,ctypes.byref(size)):return None
            return buf.value
        finally:k.CloseHandle(h)
    except (OSError,ValueError,TypeError,AttributeError):return None


def executable_version(pid):
    """Read process executable version when Windows access allows it; never launch a process."""
    path=process_image(pid)
    if not path:return None
    try:
        v=ctypes.WinDLL('version',use_last_error=True)
        v.GetFileVersionInfoSizeW.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(wintypes.DWORD)];v.GetFileVersionInfoSizeW.restype=wintypes.DWORD
        v.GetFileVersionInfoW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p];v.GetFileVersionInfoW.restype=wintypes.BOOL
        v.VerQueryValueW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(wintypes.UINT)];v.VerQueryValueW.restype=wintypes.BOOL
        size=v.GetFileVersionInfoSizeW(path,None)
        if not size:return None
        blob=ctypes.create_string_buffer(size)
        if not v.GetFileVersionInfoW(path,0,size,blob):return None
        ptr=ctypes.c_void_p();length=wintypes.UINT()
        if not v.VerQueryValueW(blob,'\\',ctypes.byref(ptr),ctypes.byref(length)) or length.value<16:return None
        fields=ctypes.cast(ptr,ctypes.POINTER(wintypes.DWORD));ms=int(fields[2]);ls=int(fields[3])
        return {'path':path,'version':[ms>>16,ms&0xffff,ls>>16,ls&0xffff]}
    except (OSError,ValueError,TypeError,AttributeError):return None


def choose_workflow(title, executable=None, project_format=None):
    """Route based on verified evidence. A version is never a guarantee of UI functionality."""
    tv=parse_title(title);ev=None
    if executable and isinstance(executable.get('version'),(list,tuple)) and executable['version']:
        ev=tuple(executable['version'][:3])
    if tv and ev and tv[0]!=ev[0]:
        return {'route':'version_conflict','detected_version':None,'version_title':tv,'version_executable':ev,
                'reason':'Window title and executable disagree; inspect About before continuing.','automatic_execution_allowed':False}
    version=tv or ev;source='window_title' if tv else ('executable_file_version' if ev else None)
    if not version:
        return {'route':'version_unknown','detected_version':None,'source':None,'automatic_execution_allowed':False,
                'next':['Inspect About and live controls; do not assume CLD, project format or menu IDs.']}
    major=version[0];minor=version[1] if len(version)>1 else None
    if major==10 and tv and ev and tv[1] is not None and len(ev)>1 and ev[1]!=tv[1]:
        return {'route':'version_conflict','detected_version':None,'version_title':tv,'version_executable':ev,
                'reason':'Prism 10 minor versions disagree; CLD availability must be checked in About.','automatic_execution_allowed':False}
    if major==10 and minor is None and ev and len(ev)>1:
        minor=ev[1];version=(major,minor,ev[2] if len(ev)>2 else None);source='window_title+executable_file_version'
    if major<8:route='legacy_pre8'
    elif major<10:route='classic_8_9'
    elif major==10 and minor is None:route='prism10_minor_unknown'
    elif major==10 and minor<2:route='modern_before_cld'
    else:route='modern_cld_capable'
    result={'route':route,'detected_version':list(version),'source':source,'version_title':tv,'version_executable':ev,
            'version_detection_does_not_prove_feature_availability':True,'project_format':project_format,
            'version_alone_allows_automatic_execution':False,'requires_capability_probe':True}
    if route in ('legacy_pre8','classic_8_9','modern_before_cld'):
        result.update(native_cld='not_available_by_version',project_strategy='create_or_open_on_target_version',
          analysis_strategy='probe_native_two_way_and_all_15_tukey; if unsupported use audited external calculation',
          annotation_strategy='static_tukey_letters_and_p_values; visually check and update after data edits',
          verification_strategy='native_high_precision_tsv_with_exclusion_flags',
          next=['Discover actual language, menus and table controls.','Use a project format supported by this installation.',
                'Confirm six groups, full two-way ANOVA and all 15 Tukey comparisons; do not substitute simple effects.',
                'Export and verify each raw table; check all letters and P texts visually.'])
    elif route=='modern_cld_capable':
        result.update(native_cld='supported_in_prism_10_2_or_later_but_must_probe',project_strategy='inspect_actual_project_format',
          analysis_strategy='probe_two_way_all_cells_tukey_and_cld',annotation_strategy='native_linked_cld_plus_static_p_text',
          verification_strategy='native_zip_if_supported_otherwise_high_precision_tsv',
          next=['Inspect actual project format, graph/analysis links, CLD and SEM; create version-compatible template.',
                'For supported native ZIP only, use validated template batch builder and native result verification.'])
    else:
        result.update(native_cld='unknown',project_strategy='inspect_actual_project_format',verification_strategy='native_export_fallback',
          next=['Find exact minor version in About; Prism 10.2 introduced CLD.','Probe actual project format and controls before choosing a template.'])
    if project_format and not project_format.get('native_zip_supported',False):
        result['native_zip_batch_builder_available']=False
        result['format_note']='Project is not a supported native ZIP; use native GUI/export fallback without claiming UID verification.'
    elif project_format:
        result['native_zip_batch_builder_available']=route=='modern_cld_capable'
    else:result['native_zip_batch_builder_available']='unknown_until_project_inspection'
    return result
