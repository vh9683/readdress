import tornado.ioloop
import tornado.web
import json
import sys
import time
import smtplib
import uuid
import mimetypes
import pickle
import email.utils
from email import encoders
from email.message import Message
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.headerregistry import Address
from tornado.log import logging, gen_log
from motor import MotorClient
from tornado.gen import coroutine
from bson import Binary
from redis import StrictRedis


OUR_DOMAIN = 'inbound.edulead.in'


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
    """ If In-Reply-To is not present, then it is assumed to be new thread
        In such a case, the from address has to be from known domain
        and allrecipients must have at least one registered user
    """
    from_email = ev['msg']['from_email']
    success = yield self.isknowndomain(from_email)
    if not success:
      return False
    for id,name in allrecipients:
      success = self.isregistereduser(id)
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
      mapped = yield self.getmapped(ev['msg']['from_email'])
      if not mapped:
        return False
      msg['From'] = email.utils.formataddr((ev['msg']['from_name'], mapped))
      gen_log.info('From: ' + str(msg['From']))
      return True

  def updateAttachments(self, ev, msg, keys):
      if 'attachments' in keys:
        for name,attachment in ev['msg']['attachments'].items():
          file_name = attachment['name']
          aType = attachment['type']
          if aType is None:
              aType = 'application/octet-stream'
          isBase64 = attachment['base64']
          maintype, subtype = aType.split('/', 1)
          if 'text' == maintype:
              part = MIMEText(attachment['content'], subtype)
          elif 'audio' == maintype:
              part = MIMEAudio(attachment['content'], subtype)
          else:
              part = MIMEBase(maintype, subtype)
              part.set_payload(attachment['content'])

          # Encode the payload using Base64
          if isBase64:
              encoders.encode_base64(part)
          # Set the filename parameter
          if file_name is not None:
              part.add_header('Content-Disposition', 'attachment', filename=file_name)
          else:
              raise ValueError("File name missing")
          msg.attach(part)

      if 'images' in keys:
        for image in ev['msg']['images'].items():
          file_name = images['name']
          aType = images['type']
          isBase64 = images['base64']
          img = MIMEImage(image['content'] ,_subtype=subtype)
          if isBase64:
              encoders.encode_base64(part)
          part.add_header('Content-Disposition', 'attachment', filename=file_name)
          msg.attach(img)

  def updatemail(self, ev, msg, keys):
      msg['Subject'] = ev['msg']['subject']
      text = ev['msg']['text']
      html = ev['msg']['html']
      part1 = MIMEText(text, 'plain')
      part2 = MIMEText(html, 'html')
      msg.attach(part1)
      msg.attach(part2)

      self.updateAttachments(ev, msg, keys)

  def sendmail(self, ev, msg, to):
    server = smtplib.SMTP('smtp.mandrillapp.com', 587)
    try:
      server.set_debuglevel(True)

      # identify ourselves, prompting server for supported features
      server.ehlo()

      # If we can encrypt this session, do it
      if server.has_extn('STARTTLS'):
        server.starttls()
        server.ehlo() # re-identify ourselves over TLS connection
        server.login('vidyartibng@gmail.com', 'c3JOgoZZ9BmKN4swnnBEpQ')

      gen_log.info('RCPT : {}'.format(to))

      composed = msg.as_string()
      gen_log.info('Actual Msg : {}'.format(composed))
      server.sendmail(ev['msg']['from_email'], to, composed)
    finally:
      server.quit()

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
        message = [ {'from':ev['msg']['from_email'], 'inboundJson':Binary(str(ev).encode(), 128)} ]
        rclient = self.settings['rclient']
        rclient.lpush('mailarchive', pickle.dumps(message))

        allrecipients = ev['msg']['to']
        if 'cc' in ev['msg']:
          allrecipients = allrecipients + ev['msg']['cc']
        
        success = yield self.validthread(ev,allrecipients)
        if not success:
          gen_log.info("Not a valid mail thread!!, dropping...")
          raise ValueError
        
        msg = MIMEMultipart('alternative')
        self.updatemail(ev, msg, keys)
        msg['X-MC-PreserveRecipients'] = 'true'
        success = yield self.populate_from_addresses(ev, msg)
        if not success:
          gen_log.info('Error adding from address')
          raise ValueError
                
        if 'Message-Id' in ev['msg']['headers']:
          msg.add_header("Message-Id", ev['msg']['headers']['Message-Id'])
        if 'In-Reply-To' in ev['msg']['headers']:
          msg.add_header("In-Reply-To", ev['msg']['headers']['In-Reply-To'])
        if 'References' in ev['msg']['headers']:
          msg.add_header("References", ev['msg']['headers']['References'])
                
        for mailid in allrecipients:
          if not self.isourdomain(mailid[0]):
            continue
          rto = yield self.mapaddrlist(allrecipients)
          actual = yield self.getactual(mailid[0])
          if not actual:
            continue
          if mailid[1]:
            recepient = email.utils.formataddr((mailid[1],actual))
            tremove = email.utils.formataddr((mailid[1],mailid[0]))
          else:
            recepient = actual
            tremove = mailid[0]
          if tremove in rto:
            rto.remove(tremove)
          if msg['From'] in rto:
            rto.remove(msg['From'])
          if 'To' in msg:
            del msg['To']
          gen_log.info('To: ' + str(rto))
          msg['To'] = ','.join(rto)

          self.sendmail(ev, msg, recepient)
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
