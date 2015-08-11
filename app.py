import tornado.ioloop
import tornado.web
import json
import sys
import time
import uuid
import mimetypes
import pickle
import email.utils
import base64
from email import encoders
from email.message import Message
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.headerregistry import Address
from tornado.log import logging, gen_log
from motor import MotorClient
from tornado.gen import coroutine
from redis import StrictRedis
import copy
import email.utils 
from email.utils import parseaddr
import logging
import logging.handlers

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class RecvHandler(tornado.web.RequestHandler):
  def write_error(self,status_code,**kwargs):
    self.set_status(200)
    self.write({'status': 200})
    self.finish()
    return

  def getdomain(self,a):
    return a.split('@')[-1]
  
  def getuserid(self,a):
    return a.split('@')[0]

  def isourdomain(self, a):
    return self.getdomain(a) == OUR_DOMAIN

  @coroutine
  def isknowndomain(self,a):
    if self.isourdomain(a):
      return True
    inbounddb = self.settings['inbounddb']
    known = yield inbounddb.domains.find_one({'domain': self.getdomain(a)})
    if not known:
      return False
    return True

  def valid_uuid4(self,a):
    userid = self.getuserid(a)
    try:
      val = uuid.UUID(userid, version=4)
    except ValueError:
      # If it's a value error, then the string 
      # is not a valid hex code for a UUID.
      return False

    # If the uuid_string is a valid hex code, 
    # but an invalid uuid4,
    # the UUID.__init__ will convert it to a 
    # valid uuid4. This is bad for validation purposes.
    return val.hex == userid

  def isregistereduser(self,a):
    """ check whether the user address is a registered one or generated one """
    return not self.valid_uuid4(a)

  @coroutine
  def isUserEmailTaggedForLI(self, a):
    """ Check if the user address is tagged for LI """
    user = yield self.getuser(a)
    if user and 'tagged' in user: 
      return user['tagged']
    return None

  @coroutine
  def validthread(self,ev,allrecipients):
    """ 
        Every new thread must come from known domain and
        and very mail must have at least one regiestered user
        who can be the sender or recepient
    """
    from_email = ev['msg']['from_email']
    if "Message-Id" not in ev["msg"]["headers"]:
      return False
    rclient = self.settings["rclient"]
    mid = pickle.loads(rclient.get(ev["msg"]["headers"]["Message-Id"]))
    if mid and mid == from_email:
      return False
    rclient.set(ev["msg"]["headers"]["Message-Id"],pickle.dumps(from_email))
    for id,name in allrecipients:
      success = self.isregistereduser(id)
      if success:
        return True
    success = yield self.getuser(from_email)
    if success:
      return True
    return False

  @coroutine
  def getuser(self,a):
    inbounddb = self.settings['inbounddb']
    if self.isourdomain(a):
      user = yield inbounddb.users.find_one({'mapped': a})
    else:
      user = yield inbounddb.users.find_one({'actual': a})
    return user

  @coroutine
  def getmapped(self,a):
    user = yield self.getuser(a)
    if not user:
      return None
    return user['mapped']

  @coroutine
  def getactual(self,a):
    user = yield self.getuser(a)
    if not user:
      return None
    return user['actual']

  @coroutine
  def newmapaddr(self,a):
    mapped = yield self.getmapped(a)
    if not mapped:
      mapped = uuid.uuid4().hex+'@'+OUR_DOMAIN
      yield inbounddb.users.insert({'mapped': mapped, 'actual': a})
      gen_log.info('insterted new ext user ' + a + ' -> ' + mapped)
    return mapped

  @coroutine
  def mapaddrlist(self, li):
    rli = []
    gen_log.info('mapaddrlist li ' + str(li))
    for x in li:
      mapped = yield self.getmapped(x[0])
      if not mapped:
        continue
      if x[1]:
        rli.append(email.utils.formataddr((x[1],mapped)))
      else:
        rli.append(mapped)
    gen_log.info('mapaddrlist rli ' + str(rli))
    return rli

  @coroutine
  def populate_from_addresses(self, ev, msg):
      mapped = yield self.newmapaddr(ev['msg']['from_email'])
      if not mapped:
        return False
      msg['From'] = email.utils.formataddr((ev['msg']['from_name'], mapped))
      gen_log.info('From: ' + str(msg['From']))
      return True

  def updateAttachments(self, ev, msg):
      if 'attachments' in ev['msg']:
        for name,attachment in ev['msg']['attachments'].items():
          file_name = attachment['name']
          aType = attachment['type']
          if aType is None:
              aType = 'application/octet-stream'
          isBase64 = attachment['base64']
          maintype, subtype = aType.split('/', 1)
          gen_log.info("MAIN TYPE {} SUB TYPE {} ".format(maintype, subtype))
          if 'text' == maintype:
              part = MIMEText(attachment['content'], subtype)
              if isBase64:
                encoders.encode_base64(part)
          elif 'audio' == maintype:
              part = MIMEAudio(attachment['content'], subtype)
              if isBase64:
                encoders.encode_base64(part)
          elif 'image' == maintype:
              imgattachment = attachment['content']
              if isBase64:
                part = MIMEImage(None, _subtype=subtype)
                part.set_payload(imgattachment)
              else:
                part = MIMEImage(imgattachment, _subtype=subtype)
          elif 'application' == maintype and 'pdf' == subtype:
              content = (attachment['content'])
              if isBase64:
                #epart = base64.b64decode(content)
                part = MIMEApplication(None, subtype)
                part.set_payload(content)
              else:
                part = MIMEApplication(content, subtype)
              part.add_header('Content-ID', '<pdf>')
          else:
              part = MIMEBase(maintype, subtype)
              content = (attachment['content'])
              if isBase64:
                #epart = base64.b64decode(content)
                part.set_payload(content)
              else:
                part.set_payload(content)
                encoders.encode_base64(part)


          # Encode the payload using Base64, use this for non image attachments
          #if isBase64 and not ('image' == maintype):
          #    encoders.encode_base64(part)
          # Set the filename parameter
          if file_name is not None:
              part.add_header('Content-Disposition', 'attachment', filename=file_name)
          else:
              raise ValueError("File name missing")

          msg.attach(part)

      if 'images' in ev['msg']:
        #gen_log.info("IMAGEs {}".format(json.dumps(ev['msg']['images'], indent=4)))
        for image in ev['msg']['images'].items():
          #gen_log.info("IMAGE {}".format(json.dumps(image, indent=2)))
          file_name = image['name']
          aType = image['type']
          isBase64 = image['base64']
          epart = base64.b64decode(attachment['content'])
          img = MIMEImage(epart, _subtype=subtype)
          #if isBase64:
          #    encoders.encode_base64(part)
          ''' 
            need to handle Content-Disposition when its inlined ... mandrill might not support inline contents
          '''
          part.add_header('Content-Disposition', 'attachment', filename=file_name)
          msg.attach(img)

  def updatemail(self, ev, msg):
      msg['Subject'] = ev['msg']['subject']
      text = ev['msg']['text']
      html = ev['msg']['html']
      part1 = MIMEText(text, 'plain')
      part2 = MIMEText(html, 'html')
      msg.attach(part1)
      msg.attach(part2)

      self.updateAttachments(ev, msg)

  def sendmail(self, evKey, msg, to):
    rclient = self.settings['rclient']
    key = uuid.uuid4().hex + ',' + evKey
    rclient.set(key, pickle.dumps((to, msg)))
    ''' mark key to exipre after 15 secs'''
    key = key.encode()
    rclient.expire(key, 25)
    rclient.lpush('sendmail', key)
    return


  @coroutine
  def post(self):
    gen_log.info('inbound recv hit!')
    ev = self.get_argument('mandrill_events',False)
    if not ev:
      raise ValueError
    else:
      localtime = time.asctime( time.localtime(time.time()) )
      localtime = localtime.replace(' ', '_')
      localtime = localtime.replace(':', '_')
      jsonfile='/tmp/inbound/Json_mail_' + localtime + '.txt'
      with open(jsonfile, 'w') as outfile:
          outfile.write(str(ev))
          outfile.close()

      ev = json.loads(ev, "utf-8")
      ev = ev[0]
      if ev['msg']['spam_report']['score'] >= 5:
        gen_log.info('Spam!! from ' + ev['msg']['from_email'])
      else:
        ''' stage 1 do mail archive for all mails '''
        rclient = self.settings['rclient']

        ''' Push the entire json to mailhandler thread through redis list'''
        pickledEv = pickle.dumps(ev)
        rclient.lpush('mailhandler', pickledEv)

        del pickledEv
        del ev

    self.set_status(200)
    self.write({'status': 200})
    self.finish()
    return

#       allrecipients = ev['msg']['to']
#       if 'cc' in ev['msg']:
#         allrecipients = allrecipients + ev['msg']['cc']

#       taggedList = []
#       for mailid,name in allrecipients:
#         if self.isUserEmailTaggedForLI(mailid):
#           taggedList.append(mailid)

#       if self.isUserEmailTaggedForLI(ev['msg']['from_email']):
#           taggedList.append(ev['msg']['from_email'])

#       ''' stage 2 check for Law Interception for all mails '''
#       if len(taggedList):
#         item = []
#         item.append(','.join(taggedList))
#         item.append(ev)
#         rclient.lpush('liarchive', pickle.dumps(item))
#       
#       success = yield self.validthread(ev,allrecipients)
#       if not success:
#         gen_log.info("Not a valid mail thread!!, dropping...")
#         raise ValueError
#       
#       msg = MIMEMultipart('alternative')
#       self.updatemail(ev, msg)
#       msg['X-MC-PreserveRecipients'] = 'true'
#       success = yield self.populate_from_addresses(ev, msg)
#       if not success:
#         gen_log.info('Error adding from address')
#         raise ValueError
#               
#       if 'Message-Id' in ev['msg']['headers']:
#         msg.add_header("Message-Id", ev['msg']['headers']['Message-Id'])
#       if 'In-Reply-To' in ev['msg']['headers']:
#         msg.add_header("In-Reply-To", ev['msg']['headers']['In-Reply-To'])
#       if 'References' in ev['msg']['headers']:
#         msg.add_header("References", ev['msg']['headers']['References'])
#               
#       evKey =  uuid.uuid4().hex
#       rclient.set(evKey, pickle.dumps(ev))
#       ''' mark key to exipre after REDIS_MAIL_DUMP_EXPIRY_TIME secs '''
#       ''' Assuming all mail clients to sendmail witn in REDIS_MAIL_DUMP_EXPIRY_TIME '''
#       rclient.expire(evKey, REDIS_MAIL_DUMP_EXPIRY_TIME)
#       mail_count = 0
#       for mailid in allrecipients:
#         if not self.isourdomain(mailid[0]):
#           continue
#         rto = yield self.mapaddrlist(allrecipients)
#         actual = yield self.getactual(mailid[0])
#         if not actual:
#           continue
#         if mailid[1]:
#           recepient = email.utils.formataddr((mailid[1],actual))
#           tremove = email.utils.formataddr((mailid[1],mailid[0]))
#         else:
#           recepient = actual
#           tremove = mailid[0]
#         if tremove in rto:
#           rto.remove(tremove)
#         if msg['From'] in rto:
#           rto.remove(msg['From'])
#         if 'To' in msg:
#           del msg['To']
#         gen_log.info('To: ' + str(rto))
#         msg['To'] = ','.join(rto)

#         self.sendmail(evKey, msg, recepient)


  def head(self):
   gen_log.info('recv head hit!')
   self.set_status(200)
   self.write({'status': 200})
   self.finish()
   return
 
logging.basicConfig(stream=sys.stdout,level=logging.DEBUG)

inbounddb = MotorClient().inbounddb
rclient = StrictRedis()

settings = {"static_path": "frontend/Freeze/",
            "template_path": "frontend/Freeze/html/",
            "inbounddb": inbounddb,
            "rclient": rclient,
}

application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/recv", RecvHandler),
    (r"/(.*)", tornado.web.StaticFileHandler,dict(path=settings['static_path'])),
], **settings)

if __name__ == "__main__":
    application.listen(8985)
    tornado.ioloop.IOLoop.current().start()
