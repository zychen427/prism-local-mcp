import copy,sys,tomllib,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from install import migrate_config
SERVER={'command':'C:/test/python.exe','args':['-X','utf8','C:/test/server.py'],'cwd':'C:/test','startup_timeout_sec':20,'tool_timeout_sec':90,'enabled':True,'env':{'PYTHONUTF8':'1'}}
class Migration(unittest.TestCase):
 def test_existing_and_preservation(self):
  old='[mcp_servers.other]\ncommand="other"\n\n[mcp_servers.prism_factorial_local]\ncommand="factor"\nenabled=true\n[mcp_servers.prism_factorial_local.env]\nA="b"\n'
  new,changed=migrate_config(old,SERVER); self.assertTrue(changed);obj=tomllib.loads(new)
  self.assertFalse(obj['mcp_servers']['prism_factorial_local']['enabled']);self.assertEqual(obj['mcp_servers']['prism_local'],SERVER)
  self.assertEqual(obj['mcp_servers']['other'],{'command':'other'});self.assertEqual(obj['mcp_servers']['prism_factorial_local']['env'],{'A':'b'})
  self.assertFalse(migrate_config(new,SERVER)[1])
 def test_custom_config_rejected(self):
  with self.assertRaises(ValueError):migrate_config('[mcp_servers.prism_local]\ncommand="custom"\n',SERVER)
if __name__=='__main__':unittest.main()
