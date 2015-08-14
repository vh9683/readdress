import tornado.ioloop
import tornado.web
import json
import sys
import uuid
import pickle
import re
from tornado.log import logging, gen_log
from tornado.httpclient import AsyncHTTPClient
from motor import MotorClient
from tornado.gen import coroutine
from redis import StrictRedis

OUR_DOMAIN = "readdress.io"

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class VerifyHandler(tornado.web.RequestHandler):
  @coroutine
  def get(self,sessionid):
    rclient = self.settings['rclient']
    gen_log.info('sessionid ' + str(sessionid))
    if not sessionid:
      self.render("sorry.html",reason="Invalid Session. This link is not valid")
      return
    session = rclient.get(sessionid)
    if not session:
      self.render("sorry.html",reason="Invalid Session. This link is not valid")
      return
    session = pickle.loads(session)
    if not session:
      self.render("sorry.html",reason="Invalid Session. This link is not valid")
      return
    http_client = AsyncHTTPClient()
    response = yield http_client.fetch("https://cognalys.com/api/v1/otp/?app_id="+self.settings['coganlys_app_id']+"&access_token="+self.settings['cognalys_acc_token']+"&mobile="+session['phonenum'],raise_error=False)
    if response.code != 200:
      gen_log.warning('coganlys auth failed - response data ' + resdata)
      self.render("sorry.html",reason="Invalid Session. This link is not valid")
      return      
    resdata = json.loads(response.body.decode())
    gen_log.info('coganlys auth response data ' + str(resdata))
    if resdata['status'] != 'success':
      self.render("sorry.html",reason="Invalid Session. This link is not valid")
      return
    session['keymatch'] = resdata['keymatch']
    session['otpstart'] = resdata['otp_start']
    rclient.setex(sessionid,600,pickle.dumps(session))
    self.render("verify.html",url="/verify/"+sessionid,ostart=resdata['otp_start'])
    return
  
  @coroutine
  def post(self,sessionid):
    rclient = self.settings['rclient']
    gen_log.info('sessionid ' + str(sessionid))
    if not sessionid:
      self.render("sorry.html",reason="Invalid Session. This link is not valid")
      return
    session = rclient.get(sessionid)
    if not session:
      self.render("sorry.html",reason="Invalid Session. This link is not valid")
      return
    session = pickle.loads(session)
    if not session:
      self.render("sorry.html",reason="Invalid Session. This link is not valid")
      return
    otp = self.get_argument('otp','junk')
    pluscode = self.get_argument('pluscode','BADCODE')
    http_client = AsyncHTTPClient()
    response = yield http_client.fetch("https://cognalys.com/api/v1/otp/confirm/?app_id="+self.settings['coganlys_app_id']+"&access_token="+self.settings['cognalys_acc_token']+"&keymatch="+session['keymatch']+"&otp="+session['otpstart']+otp,raise_error=False)
    if response.code != 200:
      gen_log.warning('coganlys verify failed - response data ' + resdata + ' request was ' + self.body['otp'])
      self.render("sorry.html",reason="Invalid OTP. Please retry with correct OTP")
      return
    resdata = json.loads(response.body.decode())
    gen_log.info('coganlys verify response data ' + str(resdata))
    if resdata['status'] != 'success':
      self.render("sorry.html",reason="Invalid OTP. Please retry with correct OTP")
      return
    inbounddb = self.settings['inbounddb']
    user = yield inbounddb.users.find_one({'actual': session['actual']})
    if user:
      yield inbounddb.users.update({'actual': session['actual']}, {'$set': {'mapped': session['mapped'], 'pluscode': pluscode, 'name': session['name']}})
    else:
      yield inbounddb.users.insert({'actual': session['actual'], 'mapped': session['mapped'], 'pluscode': pluscode, 'name': session['name']})
    rclient.delete(sessionid)
    self.set_status(200)
    reason = "Verificaton Sucessful. You can now use " + session['mapped'] + " as email id."
    msg = {'template_name': 'readdresswelcome', 'email': from_email, 'global_merge_vars': [{'name': 'name', 'content': session['name']},{'name': 'id', 'content': session['mapped']}]}
    count = rclient.publish('mailer',pickle.dumps(msg))
    gen_log.info('message ' + str(msg))
    gen_log.info('message published to ' + str(count))
    self.render("success.html",reason=reason)
    return

class SignupHandler(tornado.web.RequestHandler):
  def write_error(self,status_code,**kwargs):
    self.set_status(200)
    self.write({'status': 200})
    self.finish()
    return
  
  def getdomain(self,a):
    return a.split('@')[-1]
  
  def isourdomain(self, a):
    return self.getdomain(a) == OUR_DOMAIN

  @coroutine
  def getuser(self,a):
    inbounddb = self.settings['inbounddb']
    if self.isourdomain(a):
      user = yield inbounddb.users.find_one({'mapped': a})
    else:
      user = yield inbounddb.users.find_one({'actual': a})
    return user

  @coroutine
  def post(self):
    ev = self.get_argument('mandrill_events',False)
    if not ev:
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
    ev = json.loads(ev, "utf-8")
    ev = ev[0]
    from_email = ev['msg']['from_email']
    from_name = ev['msg']['from_name']
    if from_name is None or from_name is '':
      from_name = 'There'
    phonenum = ev['msg']['subject']
    reobj = self.settings['reobj']
    if not reobj.fullmatch(phonenum):
      msg = {'template_name': 'readdressfailure', 'email': from_email, 'global_merge_vars': [{'name': 'reason', 'content': "Invalid phone number given, please check and retry with correct phone number"}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
    user = yield self.getuser(phonenum[1:]+'@'+OUR_DOMAIN)
    if user:
      msg = {'template_name': 'readdressfailure', 'email': from_email, 'global_merge_vars': [{'name': 'reason', 'content': "Phone number given already associated with an email id, please check and retry with different phone number"}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
    session = {'actual': from_email, 'mapped': phonenum[1:]+'@'+OUR_DOMAIN, 'phonenum': phonenum, 'name': from_name}
    sessionid = uuid.uuid4().hex
    rclient = self.settings['rclient']
    rclient.setex(sessionid,600,pickle.dumps(session))
    msg = {'template_name': 'readdrsignup', 'email': from_email, 'global_merge_vars': [{'name': 'sessionid', 'content': sessionid}]}
    count = rclient.publish('mailer',pickle.dumps(msg))
    gen_log.info('message ' + str(msg))
    gen_log.info('message published to ' + str(count))
    self.set_status(200)
    self.write({'status': 200})
    self.finish()
    return    

class RecvHandler(tornado.web.RequestHandler):
  def write_error(self,status_code,**kwargs):
    self.set_status(200)
    self.write({'status': 200})
    self.finish()
    return
  
  def post(self):
    ignored = ['signup@readdress.io','noreply@readdress.io']
    gen_log.info('inbound recv hit!')
    ev = self.get_argument('mandrill_events',False)
    if not ev:
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
    else:
      ev = json.loads(ev, "utf-8")
      ev = ev[0]

      for to,toname in ev['msg']['to']:
        if to in ignored:
          self.set_status(200)
          self.write({'status': 200})
          self.finish()
          return
     
      ''' stage 1 do mail archive for all mails '''
      rclient = self.settings['rclient']

      ''' Push the entire json to mailhandler thread through redis list'''
      pickledEv = pickle.dumps(ev)
      rclient.lpush('mailhandler', pickledEv)

      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return

  def head(self):
   gen_log.info('recv head hit!')
   self.set_status(200)
   self.write({'status': 200})
   self.finish()
   return
 
logging.basicConfig(stream=sys.stdout,level=logging.DEBUG)

inbounddb = MotorClient().inbounddb
rclient = StrictRedis()
reobj = re.compile("\+[0-9]{8,16}$")

settings = {"static_path": "frontend/Freeze/",
            "template_path": "frontend/Freeze/html/",
            "inbounddb": inbounddb,
            "rclient": rclient,
            "reobj": reobj,
            "coganlys_app_id": "679106064d7f4c5692bcf28",
            "cognalys_acc_token": "8707b5cec812cd940f5e80de3c725573547187af",
}

application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/recv", RecvHandler),
    (r"/verify/(.*)", VerifyHandler),
    (r"/signup", SignupHandler),
    (r"/(.*)", tornado.web.StaticFileHandler,dict(path=settings['static_path'])),
], **settings)

if __name__ == "__main__":
    application.listen(8985)
    tornado.ioloop.IOLoop.current().start()
