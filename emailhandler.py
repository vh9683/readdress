#! /usr/bin/python3.4

import sys
from redis import StrictRedis
from bson import Binary
import base64
import pymongo
import pickle
import logging
import logging.handlers
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
i

FILESIZE=1024*1024*1024 #1MB
instance = "0"
try:
  conn=pymongo.MongoClient()
  print ("Connected successfully!!!")
except pymongo.errors.ConnectionFailure as e:
  print ("Could not connect to MongoDB: %s" % e )

db = conn.inbounddb
rclient = StrictRedis()
logger = logging.getLogger('mailHandler')
formatter = logging.Formatter('MAILHANDLER-['+instance+']:%(asctime)s %(levelname)s - %(message)s')
hdlr = logging.handlers.RotatingFileHandler('/var/tmp/mailhandler.log', 
                                            maxBytes=FILESIZE, backupCount=10)
hdlr.setFormatter(formatter)
logger.addHandler(hdlr) 
logger.setLevel(logging.DEBUG)

OUR_DOMAIN = 'inbound.edulead.in'

REDIS_MAIL_DUMP_EXPIRY_TIME = 60

def getdomain(a):
  return a.split('@')[-1]
  
def getuserid(a):
  return a.split('@')[0]

def isourdomain( a):
  return getdomain(a) == OUR_DOMAIN

def isknowndomain(a):
  if isourdomain(a):
    return True
  known = yield db.domains.find_one({'domain': getdomain(a)})
  if not known:
    return False
  return True

def getuser(a):
  if isourdomain(a):
    user = db.inbounddb.users.find_one({'mapped': a})
  else:
    user = db.inbounddb.users.find_one({'actual': a})
  return user

def getmapped(a):
  user = getuser(a)
  if not user:
    return None
  return user['mapped']

def newmapaddr(a):
  mapped = getmapped(a)
  if not mapped:
    mapped = uuid.uuid4().hex+'@'+OUR_DOMAIN
    db.inbounddb.users.insert({'mapped': mapped, 'actual': a})
    logger.info('insterted new ext user ' + a + ' -> ' + mapped)
  return mapped

def populate_from_addresses(msg):
  fromstring = msg['From']
  fromname, fromemail = parseaddr(fromstring)
  mapped = newmapaddr(fromemail)
  if not mapped:
    return False
  del msg['From']
  if fromname:
    msg['From'] = email.utils.formataddr((fromname, mapped))
  else:
    msg['From'] = mapped
  logger.info('From: ' + str(msg['From']))
  return True, fromemail

def getToAddresses(msg):
  tostr = msg.get('To')
  tolst = tostring.split(',')
  tolst = [to.strip() for to in tolst if not 'undisclosed-recipient' in to]
  torecipients = []
  for toaddr in tolst:
    toname,to  = parseaddr(toaddr)
    to = [to, toname]
    torecipients.append(to)
  return torecipients

def getCcAddresses(msg):
  ccstr = msg.get('Cc')
  cclst = ccstring.split(',')
  cclst = [cc.strip() for cc in cclst if not 'undisclosed-recipient' in cc]
  ccrecipients = []
  for ccaddr in cclst:
    ccname,cc  = parseaddr(ccaddr)
    cc = [cc, ccname]
    ccrecipients.append(cc)
  return ccrecipients
 

def checkForBccmail (msg):
  receivedhrds = msg.get_all('Received')
  bccinmail = False
  bccemail = []
  for hdr in receivedhrds:
    match = re.search('([\w.-]+)@([\w.-]+)', hdr)
    if match is not None:
      mailaddr = match.group()
      bccinmail = True
      bccemail.append(mailaddr)
    
  if bccinmail:
    logger.info('Mail contains BCC email addresses in Received Header... Dropping Mail')
    logger.info("Bcc Emails Addresses are : {}".format( ', '.join(bccemail)))

  return bccinmail

def valid_uuid4(a):
  userid = getuserid(a)
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

def isregistereduser(a):
  """ check whether the user address is a registered one or generated one """
  return not valid_uuid4(a)

def validthread(msg,allrecipients,from_email):
  """ 
      Every new thread must come from known domain and
      and very mail must have at least one regiestered user
      who can be the sender or recepient
  """
  msgId = msg.get("Message-ID") 
  if msgId is None:
    return False

  mid = pickle.loads(rclient.get(msgId))
  if mid and mid == from_email:
    return False
  rclient.set(msgId,pickle.dumps(from_email))

  for id,name in allrecipients:
    success = isregistereduser(id)
    if success:
      return True
  success = yield getuser(from_email)
  if success:
    return True
  return False

def isUserEmailTaggedForLI(a):
  """ Check if the user address is tagged for LI """
  user = getuser(a)
  if user and 'tagged' in user: 
    return user['tagged']
  return None

def getactual(a):
  user = getuser(a)
  if not user:
    return None
  return user['actual']


def mapaddrlist(li):
  rli = []
  logger.info('mapaddrlist li ' + str(li))
  for x in li:
    mapped = getmapped(x[0])
    if not mapped:
      continue
    if x[1]:
      rli.append(email.utils.formataddr((x[1],mapped)))
    else:
      rli.append(mapped)
  logger.info('mapaddrlist rli ' + str(rli))
  return rli

def sendmail( evKey, msg, to):
  key = uuid.uuid4().hex + ',' + evKey
  rclient.set(key, pickle.dumps((to, msg)))
  ''' mark key to exipre after 15 secs'''
  key = key.encode()
  rclient.expire(key, 25)
  rclient.lpush('sendmail', key)
  return

if __name__ == '__main__':
  instance = sys.argv[-1]

  if not instance:
    instance = "1"

  ''' 
    SPAM check is not done here ... it should have been handled in earlier stage of pipeline
  '''
  while True:
    item = rclient.brpoplpush('mailhandler', 'mailhandlerBackUp')
    ev = pickle.loads(item)
    emaildump = (ev['msg']['raw_msg'])
    origmsg = email.message_from_string(emaildump)
    ''' Just to keep back up of orig mail'''
    msg = copy.deepcopy(origmsg)
    del msg['DKIM-Signature']
    
    if checkForBccmail(msg):
      #Dropping mail
      continue
   
    ''' handle ev msg here 
        1) parse raw msg
        2) check for validity
        3) check if bcc mail and drop the mail / do some thing
        4) move the completed section to other parts such as li / sendmail or some thing else
    '''
    torecipients = getToAddresses(msg)
    ccrecipients = getCcAddresses(msg)
    allrecipients = torecipients + ccrecipients
    del msg['To']
    del msg['Cc']

    success,fromemail= populate_from_addresses(msg)
    if not success:
      logger.info('Error adding from address')
      raise ValueError

    taggedList = []
    for mailid,name in allrecipients:
      if isUserEmailTaggedForLI(mailid):
        taggedList.append(mailid)

    if isUserEmailTaggedForLI(fromemail):
        taggedList.append(fromemail)

    ''' stage 2 check for Law Interception for all mails '''
    if len(taggedList):
      item = []
      item.append(','.join(taggedList))
      item.append(ev)
      rclient.lpush('liarchive', pickle.dumps(item))
       
    success = validthread(msg, allrecipients, fromemail)
    if not success:
      logger.info("Not a valid mail thread!!, dropping...")
      raise ValueError
    msg['X-MC-PreserveRecipients'] = 'true'

    ''' msg will have Message-ID In-ReplyTo and References '''
    #if 'Message-Id' in ev['msg']['headers']:
    #  msg.add_header("Message-Id", ev['msg']['headers']['Message-Id'])
    #if 'In-Reply-To' in ev['msg']['headers']:
    #  msg.add_header("In-Reply-To", ev['msg']['headers']['In-Reply-To'])
    #if 'References' in ev['msg']['headers']:
    #  msg.add_header("References", ev['msg']['headers']['References'])
               
    evKey =  uuid.uuid4().hex
    rclient.set(evKey, pickle.dumps(ev))
    ''' mark key to exipre after REDIS_MAIL_DUMP_EXPIRY_TIME secs '''
    ''' Assuming all mail clients to sendmail witn in REDIS_MAIL_DUMP_EXPIRY_TIME '''
    rclient.expire(evKey, REDIS_MAIL_DUMP_EXPIRY_TIME)
    mail_count = 0
    for mailid in allrecipients:
      if not isourdomain(mailid[0]):
        continue
      rto = mapaddrlist(allrecipients)
      actual = getactual(mailid[0])
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
      logger.info('To: ' + str(rto))
      msg['To'] = ','.join(rto)
      sendmail(evKey, msg, recepient)
 
    print ('len of mailhandlerBackUp is : {}'.format(r.llen('mailhandlerBackUp')))
    rclient.lrem('mailhandlerBackUp', 0, item)
    print ('len of mailhandlerBackUp is : {}'.format(r.llen('mailhandlerBackUp')))

    del origmsg
    del msg
    del ev
