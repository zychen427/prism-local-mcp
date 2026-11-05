"""Conservative, evidence-based Prism compatibility screening; never mutates files."""
import hashlib,json,re,zipfile
from pathlib import Path

SOURCES={'files':'https://www.graphpad.com/guides/prism/latest/user-guide/compatibility_between_prism_versions.htm',
         'cld':'https://www.graphpad.com/updates/prism-10-2-0-release-notes',
         'script':'https://www.graphpad.com/support/faq/can-all-of-the-features-of-graphpad-be-specified-through-a-scripting-language/'}

def _version(value):
    if value is None:return None
    m=re.search(r'(?<!\d)(\d{1,2})(?:\.(\d{1,3}))?(?:\.(\d{1,3}))?',str(value))
    return tuple(int(x) if x is not None else None for x in m.groups()) if m else None

def screen(version,feature='open_project',project_file=None):
    if feature not in ('open_project','ordinary_graph','native_cld','native_ic20_template'):
        raise ValueError('feature must be open_project, ordinary_graph, native_cld or native_ic20_template')
    v=_version(version); result={'target_version':list(v) if v else None,'feature':feature,'sources':SOURCES,'status':'unknown','update_recommended':False,'warnings':[],'input_is_not_live_detection':True}
    if not v:
        result['warnings'].append('Unable to determine Prism version. Inspect About and rerun.');return result
    major,minor,patch=v
    project=None
    if project_file:
        p=Path(project_file).resolve()
        if not p.is_file():raise FileNotFoundError(f'Project file not found: {p}')
        project={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'format':'unrecognized','declared_minimum_prism_version':None}
        if zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                if 'document.json' in z.namelist():
                    info=z.getinfo('document.json')
                    if info.file_size>2_000_000:raise ValueError('Unexpected document.json size.')
                    d=json.loads(z.read(info));project.update(format='prism_native_zip',declared_minimum_prism_version=d.get('minPrismVersion'),created_by=d.get('createdBy',{}).get('version'),modified_by=d.get('modifiedBy',{}).get('version'))
        result['project']=project
    if feature=='native_cld':
        if major<10 or (major==10 and minor is not None and minor<2):
            result.update(status='incompatible',update_recommended=True,minimum_version='10.2.0');result['warnings'].append('Native CLD requires Prism 10.2 or newer; a nonlinked static annotation is an alternative.')
        elif major==10 and minor is None: result['warnings'].append('Prism 10 minor version is unknown; verify About before CLD.')
        else:result['status']='supported_by_version_only';result['warnings'].append('Inspect the actual analysis and UI; version alone does not prove availability.')
    elif feature=='native_ic20_template':
        if major!=11:result.update(status='implementation_unverified',update_recommended=False);result['warnings'].append('This MCP template was tested in Prism 11; do not assume it works in other versions. Verify or use a local-version template.')
        else:result.update(status='implementation_version_match',update_recommended=False);result['warnings'].append('This checks the tested major version only; template hash, data shape, UI language and live capability remain to be verified.')
    elif feature=='ordinary_graph':
        result['status']='requires_capability_probe';result['warnings'].append('Ordinary graphing does not itself require Prism 10.2 or CLD; check the actual table, graph template, version and UI.')
    if project and project['format']=='prism_native_zip':
        if major<10:
            result.update(status='incompatible',update_recommended=True);result['warnings'].append('Recognized .prism native ZIP requires Prism 10 or newer; update or request a compatible legacy export, which may lose features.')
        elif project['declared_minimum_prism_version']:
            minimum=_version(project['declared_minimum_prism_version']); have=tuple(x or 0 for x in v)
            if minimum and any(v[i] is None and minimum[i] not in (None,0) for i in range(3)) and have<tuple(x or 0 for x in minimum):
                result['warnings'].append('The target version is incomplete; compare the exact patch version before opening.')
            elif minimum and have<tuple(x or 0 for x in minimum):
                result.update(status='incompatible',update_recommended=True,minimum_version=project['declared_minimum_prism_version']);result['warnings'].append('Project declares a minimum Prism version newer than the target; update before opening.')
            elif feature=='open_project':result['status']='declared_minimum_satisfied';result['warnings'].append('Declared minimum is met; this is not a guarantee that every newer feature will be editable.')
        elif feature=='open_project':result['warnings'].append('Native ZIP lacks a readable minimum version; version compatibility is not proven.')
    elif project and feature=='open_project':result['warnings'].append('Legacy or unknown file contents are not inferred from filename; open on a copy and use Prism compatibility checker.')
    if feature=='open_project' and not project:result['warnings'].append('Supply a project file to assess file compatibility.')
    return result
