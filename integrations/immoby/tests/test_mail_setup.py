import base64,tempfile,unittest
from pathlib import Path
from cloud.mail_setup import aruba_settings,save_settings
class Tests(unittest.TestCase):
 def test_domain_and_free_aruba_accounts_use_the_correct_tls_endpoint(self):
  for address,host in [('host@example.it','smtps.aruba.it'),('host@aruba.it','smtp.aruba.it')]:
   settings=aruba_settings(address,"example$#'password")
   self.assertEqual((settings['SMTP_HOST'],settings['SMTP_PORT'],settings['SMTP_SECURITY']),(host,'465','ssl'))
   self.assertEqual(base64.b64decode(settings['SMTP_PASSWORD_B64']).decode(),"example$#'password")
 def test_header_and_env_injection_is_rejected(self):
  for address,password in [('host@example.it\nBCC:other@example.it','p'),('host@example.it','p\nOTHER_ENV=value')]:
   with self.assertRaises(ValueError):aruba_settings(address,password)
 def test_save_preserves_other_config_and_restricts_permissions(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'.env';p.write_text('UNRELATED=keep\nSMTP_PORT=587\n')
   save_settings(p,aruba_settings('host@example.it','test$#'))
   self.assertIn('UNRELATED=keep\n',p.read_text());self.assertIn('SMTP_PORT=465\n',p.read_text());self.assertNotIn('test$#',p.read_text());self.assertEqual(p.stat().st_mode & 0o777,0o600)
if __name__=='__main__':unittest.main()
