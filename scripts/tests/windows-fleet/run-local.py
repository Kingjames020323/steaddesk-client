#!/usr/bin/env python3
"""Real PE/AuthentiCode vector generation on a non-Windows host.

This does NOT execute Windows APIs/PEs or prove Windows installation/service health.
Keys and all generated binaries are deleted with the temporary laboratory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

p=argparse.ArgumentParser()
p.add_argument('--osslsigncode',required=True,type=Path)
p.add_argument('--compiler',default='x86_64-w64-mingw32-gcc')
p.add_argument('--windres',default='x86_64-w64-mingw32-windres')
p.add_argument('--output',required=True,type=Path)
a=p.parse_args()
fixture=Path(__file__).resolve().parent

def run(args,expected=0):
 r=subprocess.run([str(x) for x in args],text=True,capture_output=True)
 if r.returncode!=expected:raise RuntimeError(f'fixture command status {r.returncode}, expected {expected}: '+r.stdout+r.stderr)
 return r

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def value(path,key):
 data=path.read_bytes();needle=(key+'\0').encode('utf-16le');at=data.find(needle)
 if at<0:return None
 assert data.find(needle,at+1)<0,'ambiguous fixture resource'
 _,count,kind=struct.unpack_from('<HHH',data,at-6);assert kind==1
 start=(at+len(needle)+3)&~3
 return data[start:start+2*count].decode('utf-16le').rstrip('\0')

with tempfile.TemporaryDirectory(prefix='steaddesk-win-authenticode-') as tmp:
 lab=Path(tmp)
 run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',lab/'key.pem','-out',lab/'cert.pem','-days','1','-subj','/CN=SteadDesk Disposable Code Signing Test','-addext','basicConstraints=critical,CA:FALSE','-addext','keyUsage=critical,digitalSignature','-addext','extendedKeyUsage=codeSigning'])
 def build(name,payload=None):
  rc=lab/(name+'.rc');obj=lab/(name+'.o');unsigned=lab/(name+'-unsigned.exe');signed=lab/(name+'.exe')
  prefix='#define FIXTURE_DESCRIPTION "SteadDesk Fleet Fixture '+name+'"\n'
  if payload is not None:prefix+='#define SD_UPD4_PAYLOAD_SHA '+json.dumps(payload)+'\n'
  rc.write_text(prefix+(fixture/'fixture.rc').read_text())
  run([a.windres,'-O','coff',rc,obj])
  run([a.compiler,'-O2','-Wall','-Wextra','-Werror',fixture/'installer_fixture.c',obj,'-ladvapi32','-o',unsigned])
  run([a.osslsigncode,'sign','-certs',lab/'cert.pem','-key',lab/'key.pem','-h','sha256','-n','SteadDesk Disposable Test','-in',unsigned,'-out',signed])
  good=run([a.osslsigncode,'verify','-CAfile',lab/'cert.pem','-in',signed])
  assert 'Signature verification: ok' in good.stdout
  return signed
 inner=build('inner');inner_hash=digest(inner)
 outer=build('outer',inner_hash);wrong=build('wrong','0'*64);malformed=build('malformed','not-a-sha256');missing=build('missing')
 assert value(outer,'SteadDeskPayloadSHA256')==inner_hash
 assert value(wrong,'SteadDeskPayloadSHA256')=='0'*64
 assert value(malformed,'SteadDeskPayloadSHA256')=='not-a-sha256'
 assert value(missing,'SteadDeskPayloadSHA256') is None
 data=bytearray(outer.read_bytes());pe=struct.unpack_from('<I',data,0x3c)[0];sections=struct.unpack_from('<H',data,pe+6)[0];optional=struct.unpack_from('<H',data,pe+20)[0]
 for i in range(sections):
  at=pe+24+optional+40*i
  if data[at:at+8].rstrip(b'\0')==b'.text':
   raw=struct.unpack_from('<I',data,at+20)[0];data[raw+16]^=1;break
 else:raise AssertionError('no fixture text section')
 tampered=lab/'tampered.exe';tampered.write_bytes(data)
 bad=run([a.osslsigncode,'verify','-CAfile',lab/'cert.pem','-in',tampered],expected=1)
 assert 'MISMATCH' in bad.stdout
 der=subprocess.check_output(['openssl','x509','-in',str(lab/'cert.pem'),'-outform','DER'])
 report={'scope':'real AMD64 PE and actual Authenticode cryptography on macOS; NO Windows API or executable/service execution','tool':run([a.osslsigncode,'--version']).stdout.splitlines()[0],'signer_cert_sha256':hashlib.sha256(der).hexdigest(),'sha256':{x.name:digest(x) for x in (inner,outer,wrong,malformed,missing,tampered)},'authenticode_valid_vectors':5,'tampered_signature_rejected':True,'payload_resource_vectors':{'matching':inner_hash,'wrong':'0'*64,'malformed':'not-a-sha256','missing':None},'fixture_source_sha256':{x.name:digest(x) for x in (fixture/'installer_fixture.c',fixture/'fixture.rc')},'windows_runtime':'NOT_RUN','secret_cleanup':'TemporaryDirectory removes keys/certificates and every generated PE'}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2,sort_keys=True))
print('Local signed PE/AuthentiCode vectors PASS; Windows runtime NOT_RUN.')
