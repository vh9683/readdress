import tornado.ioloop
import tornado.web
import json
import sys
import uuid
import pickle
import hashlib
import hmac
import base64
import datetime
import pluscodes
from tornado.log import logging, gen_log
from motor import MotorClient
from tornado.gen import coroutine
from redis import StrictRedis
from validate_email import validate_email
from  validations import PhoneValidations
from tornado.httpclient import AsyncHTTPClient
from config import ReConfig

readdress_configs = ReConfig()
#default_configs = readdress_configs.ConfigSectionMap('DEFAULT')
OUR_DOMAIN = readdress_configs.get_ourdomain()
if OUR_DOMAIN is None:
    raise ValueError("OUR_DOMAIN Not configured")

class BaseHandler(tornado.web.RequestHandler):
    def validate(self, request):
        gen_log.info('authenticatepost for ' + request.path)
        authkey = self.settings['Mandrill_Auth_Key'][request.path].encode()
        if 'X-Mandrill-Signature' in request.headers:
          rcvdsignature = request.headers['X-Mandrill-Signature']
        else:
          gen_log.info('Invalid post from ' + request.remote_ip)
          return False
        data = 'https://' + OUR_DOMAIN + request.path
        argkeys = sorted(request.arguments.keys())
        for arg in argkeys:
          data += arg
          for args in self.request.arguments[arg]:
            data += args.decode()
        hashed = hmac.new(authkey,data.encode(),hashlib.sha1)
        asignature = base64.b64encode(hashed.digest()).decode()
        gen_log.info('rcvdsignature ' + str(rcvdsignature))
        gen_log.info('asignature ' + str(asignature))
        return asignature == rcvdsignature

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
    def getmapped(self, a):
        user = yield self.getuser(a)
        if not user:
          return None
        return user['mapped']


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class TOSHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("tos.html")



class VerifyHandler(BaseHandler):
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
    self.render("verify.html",url="/verify/"+sessionid)
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
    pluscode = self.get_argument('pluscode','BADCODE')
    if not pluscodes.isFull(pluscode):
      self.render("sorry.html",reason="Invalid Plus+Code. Please retry with correct code")
      return
    inbounddb = self.settings['inbounddb']
    user = yield inbounddb.users.find_one({'actual': session['actual']})
    if user:
      yield inbounddb.users.update({'actual': session['actual']}, {'$set': {'mapped': session['mapped'], 'pluscode': pluscode, 'name': session['name'], 'phone_verified':'False', 'suspended':'False'}})
    else:
      yield inbounddb.users.insert({'actual': session['actual'], 'mapped': session['mapped'], 'pluscode': pluscode, 'name': session['name'], 'phone_verified': 'False' , 'suspended' : 'False', 'verify_count' : 0} )
    rclient.delete(sessionid)
    self.set_status(200)
    reason = "Verificaton Sucessful. You can now use " + session['mapped'] + " as email id."
    msg = {'template_name': 'readdresswelcome', 'email': session['actual'], 'global_merge_vars': [{'name': 'name', 'content': session['name']},{'name': 'id', 'content': session['mapped']}]}
    count = rclient.publish('mailer',pickle.dumps(msg))
    gen_log.info('message ' + str(msg))
    gen_log.info('message published to ' + str(count))
    self.render("success.html",reason=reason)
    return

   
class SignupHandler(BaseHandler):
  @coroutine
  def post(self):
    if self.validate(self.request):
      gen_log.info('post authenticated successfully')
    else:
      gen_log.info('post authentication failed, remote ip ' + self.request.remote_ip)
      self.set_status(400)
      self.write('Bad Request')
      self.finish()
      return
    ev = self.get_argument('mandrill_events',False)
    if not ev:
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
    rclient = self.settings['rclient']
    ev = json.loads(ev, "utf-8")
    ev = ev[0]
    from_email = ev['msg']['from_email']
    from_name = ev['msg']['from_name']
    if from_name is None or from_name is '':
      from_name = 'There'
    phonenum = ev['msg']['subject']

    phvalids = PhoneValidations(phonenum)
    if not phvalids.validate():
      msg = {'template_name': 'readdressfailure', 'email': from_email, 'global_merge_vars': [{'name': 'reason', 'content': "Invalid phone number given, please check and retry with correct phone number"}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return

    if not phvalids.is_number_valid():
      msg = {'template_name': 'readdressfailure', 'email': from_email, 'global_merge_vars': [{'name': 'reason', 'content': "Invalid phone number given, please check and retry with correct phone number"}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return

    if not phvalids.is_allowed_MCC():
      msg = {'template_name': 'readdressfailure', 'email': from_email, 'global_merge_vars': [{'name': 'reason', 'content': "This Service is not available in your Country as of now."}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return

    user = yield self.getuser(phonenum[1:]+'@'+OUR_DOMAIN)
    if user:
      msg = {'template_name': 'readdressfailure', 'email': from_email, 'global_merge_vars': [{'name': 'reason', 'content': "Phone number given is already associated with an email id, please check and retry with different phone number"}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return

    actual_user = yield self.getuser(from_email)
    if actual_user and actual_user['mapped'] != (phonenum[1:]+'@'+OUR_DOMAIN) :
      content = "This email-id {0} is already associated with another phone number, you can associate one phone number with an email id for free account.".format(from_email)
      msg = {'template_name': 'readdressfailure', 'email': from_email, 'global_merge_vars': [{'name': 'reason', 'content': content }]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
    elif actual_user and actual_user['mapped'] == (phonenum[1:]+'@'+OUR_DOMAIN) :
      content = "This email-id {0} is already associated with an phone number".format(from_email)
      msg = {'template_name': 'readdressfailure', 'email': from_email, 'global_merge_vars': [{'name': 'reason', 'content': content }]}
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


class DeregisterHandler(BaseHandler):
  @coroutine
  def post(self):
    if self.validate(self.request):
      gen_log.info('post authenticated successfully')
    else:
      gen_log.info('post authentication failed, remote ip ' + self.request.remote_ip)
      self.set_status(400)
      self.write('Bad Request')
      self.finish()
      return
    ev = self.get_argument('mandrill_events',False)
    if not ev:
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
    rclient = self.settings['rclient']
    ev = json.loads(ev, "utf-8")
    ev = ev[0]

    
    #Mail-id will be deregistered in 24 hours , mail to be sent out
    rclient = self.settings['rclient']
    ''' Push the entire json to mailhandler thread through redis list '''
    pickledEv = pickle.dumps(ev)
    rclient.lpush('mailDeregisterhandler', pickledEv)

    self.set_status(200)
    self.write({'status': 200})
    self.finish()
    return    


class ModifyHandler(BaseHandler):
  @coroutine
  def post(self):
    if self.validate(self.request):
      gen_log.info('post authenticated successfully')
    else:
      gen_log.info('post authentication failed, remote ip ' + self.request.remote_ip)
      self.set_status(400)
      self.write('Bad Request')
      self.finish()
      return
    ev = self.get_argument('mandrill_events',False)
    if not ev:
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
    rclient = self.settings['rclient']
    ev = json.loads(ev, "utf-8")
    ev = ev[0]

    #modify phone number handler
    rclient = self.settings['rclient']
    ''' Push the entire json to mailhandler thread through redis list '''
    pickledEv = pickle.dumps(ev)
    rclient.lpush('mailModifyhandler', pickledEv)

    self.set_status(200)
    self.write({'status': 200})
    self.finish()
    return    



class PluscodeHandler(BaseHandler):
  @coroutine
  def post(self):
    if self.validate(self.request):
      gen_log.info('post authenticated successfully')
    else:
      gen_log.info('post authentication failed, remote ip ' + self.request.remote_ip)
      self.set_status(400)
      self.write('Bad Request')
      self.finish()
      return
    ev = self.get_argument('mandrill_events',False)
    if not ev:
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
    ev = json.loads(ev, "utf-8")
    ev = ev[0]
    from_email = ev['msg']['from_email']
    pluscode = ev['msg']['subject']
    rclient = self.settings['rclient']
    user = yield self.getuser(from_email)
    if user:
      if not pluscodes.isFull(pluscode):
          msg = {'template_name': 'readdresspluscode', 'email': from_email, 'global_merge_vars': [{'name': 'outcome', 'content': "failed, provide correct plus+code"}]}
          count = rclient.publish('mailer',pickle.dumps(msg))
          gen_log.info('message ' + str(msg))
          gen_log.info('message published to ' + str(count))
          self.set_status(200)
          self.write({'status': 200})
          self.finish()
          return
      inbounddb = self.settings['inbounddb']
      yield inbounddb.users.update({'actual': from_email},{'$set': {'pluscode': pluscode}})
      msg = {'template_name': 'readdresspluscode', 'email': from_email, 'global_merge_vars': [{'name': 'outcome', 'content': "succeeded, do keep it updated"}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
    else:
      msg = {'template_name': 'readdresspluscode', 'email': from_email, 'global_merge_vars': [{'name': 'outcome', 'content': "failed, you haven't signed up yet, provide your correct plus+code during signup"}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return

class InviteFriendHandler(BaseHandler):
  @coroutine
  def sendInvite (self, mailid, fromname):
    gen_log.info("Sending invites from {} to {}".format(fromname, mailid))
    inbounddb = self.settings['inbounddb']
    rclient = self.settings['rclient']
    if fromname is None:
      fromname = ""
    user = yield inbounddb.invitesRecipients.find_one( { 'email' : mailid } )
    if not user:
      utc_timestamp = datetime.datetime.utcnow() + datetime.timedelta(days=30)
      user = yield inbounddb.invitesRecipients.insert( { 'email' : mailid, 'Expiry_date' : utc_timestamp } )
      msg = {'template_name': 'readdressInvite', 'email': mailid, 'global_merge_vars': [{'name': 'friend', 'content': fromname}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
    else:
      gen_log.info('Invitation already sent to {}, resending cannot be done until expiry'.format(mailid))
    return

  @coroutine
  def post(self):
    if self.validate(self.request):
      gen_log.info('post authenticated successfully')
    else:
      gen_log.info('post authentication failed, remote ip ' + self.request.remote_ip)
      self.set_status(400)
      self.write('Bad Request')
      self.finish()
      return
    ev = self.get_argument('mandrill_events',False)
    if not ev:
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
    ev = json.loads(ev, "utf-8")
    ev = ev[0]
    rclient = self.settings['rclient']
    from_email = ev['msg']['from_email']
    from_name = ev['msg']['from_name']
    friendemail = ev['msg']['subject']
    friendemail = friendemail.strip()
    if (friendemail is None) or not validate_email(friendemail):
      msg = {'template_name': 'readdressInviteFailure', 'email': from_email, 'global_merge_vars': [{'name': 'reason', 'content': "Incorrect emailid given, please check and retry with correct emailid to invite a friend "}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return

    import validations
    valids = validations.Validations()
    #only registered users can use this facility
    user = yield self.getmapped(from_email)
    gen_log.info("From user mapped {} ".format(user))
    if not user or not valids.isregistereduser(user):
      msg = {'template_name': 'readdressInviteFailure', 'email': from_email, 'global_merge_vars': [{'name': 'reason', 'content': "You haven't signed up yet, please signup to use invite others to readdress.io"}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return

    frienduser = yield self.getmapped(friendemail)
    if frienduser and valids.isregistereduser(frienduser):
      msg = {'template_name': 'readdressInviteFailure', 'email': from_email, 'global_merge_vars': [{'name': 'reason', 'content': "User <" + friendemail + "> is already registered with us"}]}
      count = rclient.publish('mailer',pickle.dumps(msg))
      gen_log.info('message ' + str(msg))
      gen_log.info('message published to ' + str(count))
      self.set_status(200)
      self.write({'status': 200})
      self.finish()
      return
        
    self.sendInvite(friendemail, from_name)
    self.set_status(200)
    self.write({'status': 200})
    self.finish()
    return
 
class RecvHandler(BaseHandler):
  def post(self):
    if self.validate(self.request):
      gen_log.info('post authenticated successfully')
    else:
      gen_log.info('post authentication failed, remote ip ' + self.request.remote_ip)
      self.set_status(400)
      self.write('Bad Request')
      self.finish()
      return

    rclient = self.settings['rclient']
    ignored =  self.settings ["ignored_in_recv"]
    ignored = ['signup@readdress.io','noreply@readdress.io','pluscode@readdress.io', 'inviteafriend@readdress.io', 'deregister@readdress.io', 'unsubscribe@readdress.io' , 'changephone@readdress.io' ]

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
 
class VerifyPhoneHandlder(BaseHandler):
    def get(self, sessionid):
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
        self.render("verifyphone.html",url="/verifyphone/"+sessionid,ostart=resdata['otp_start'])

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
        inbounddb = self.settings['inbounddb']
        user = yield inbounddb.users.find_one({'actual': session['actual']})
        if not user:
            self.render("sorry.html",reason="Invalid Session. This link is not valid")
            return
        otp = self.get_argument('otp','junk')
        http_client = AsyncHTTPClient()
        response = yield http_client.fetch("https://cognalys.com/api/v1/otp/confirm/?app_id="+self.settings['coganlys_app_id']+"&access_token="+self.settings['cognalys_acc_token']+"&keymatch="+session['keymatch']+"&otp="+session['otpstart']+otp,raise_error=False)
        if response.code != 200:
            self.render("sorry.html",reason="Invalid OTP. Please retry with correct OTP")
            return
        resdata = json.loads(response.body.decode())
        gen_log.info('coganlys verify response data ' + str(resdata))
        if resdata['status'] != 'success':
            self.render("sorry.html",reason="Invalid OTP. Please retry with correct OTP")
            return
        yield inbounddb.users.update({'actual': session['actual']}, {'$set': {'phone_verified':'True'}})
        reason = "Thank You for verifing phone number."
        self.render("success.html",reason=reason)
        return


handler='APP'
formatter=('\n'+handler+':%(asctime)s-[%(filename)s:%(lineno)s]-%(levelname)s - %(message)s')
logging.basicConfig(level=logging.DEBUG, format=formatter, stream=sys.stdout)
gen_log.info("Starting APP")
#logging.basicConfig(stream=sys.stdout,level=logging.DEBUG)

inbounddb = MotorClient().inbounddb

#expire after 30days from now
inbounddb.invitesRecipients.ensure_index("Expiry_date", expireAfterSeconds=0)

rclient = StrictRedis()

ignoredmails = ['signup@readdress.io','noreply@readdress.io','pluscode@readdress.io', 'inviteafriend@readdress.io', 'deregister@readdress.io', 'unsubscribe@readdress.io' , 'changephone@readdress.io' ]

settings = {"static_path": "frontend/Freeze/",
            "template_path": "frontend/Freeze/html/",
            "inbounddb": inbounddb,
            "rclient": rclient,
            "coganlys_app_id": "679106064d7f4c5692bcf28",
            "cognalys_acc_token": "8707b5cec812cd940f5e80de3c725573547187af",
            "Mandrill_Auth_Key": {"/recv": "27pZHL5IBNxJ_RS7PKdsMA",
                                  "/signup": "ZWNZCpFTJLg7UkJCpEUv9Q",
                                  "/pluscode": "oKkvJSC7REP5uvojOBFcfg",
                                  "/inviteafriend": "EVUgwnBc9PaIWDNksPaEzw",
                                  "/unsubscribe": "VEXYzywV5OnorzXKlu2OKg",
                                  "/changephone": "AFpsYX7y1GJ67vakDqoxpA"},
             "ignored_in_recv" : ignoredmails,
}




application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/tos", TOSHandler),
    (r"/recv", RecvHandler),
    (r"/verify/(.*)", VerifyHandler),
    (r"/signup", SignupHandler),
    (r"/pluscode", PluscodeHandler),
    (r"/inviteafriend", InviteFriendHandler),
    (r"/unsubscribe", DeregisterHandler),
    (r"/changephone", ModifyHandler),
    (r"/verifyphone/(.*)", VerifyPhoneHandlder),
    (r"/(.*)", tornado.web.StaticFileHandler,dict(path=settings['static_path'])),
], **settings)

if __name__ == "__main__":
    application.listen(8985)
    tornado.ioloop.IOLoop.current().start()
