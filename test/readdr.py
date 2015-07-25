import json
import smtplib
import sys
import uuid
import base64
import mimetypes
import email.utils
from email import encoders
from email.message import Message
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.headerregistry import Address


OUR_DOMAIN = 'inbound.edulead.in'

mailmap = {}
mailmap['919686111887@inbound.edulead.in'] = 'badariprasad.h@gmail.com'
mailmap["919845837392@inbound.edulead.in"] = 'badari.hp@outlook.com'
mailmap["badari.hp@inbound.edulead.in"]  = 'badari.ph@gmail.com'
mailmap['919035295469@inbound.edulead.in']     = 'harish.v.murthy@gmail.com'
mailmap['testingmail@inbound.edulead.in'] = 'badari.hp@gmail.com'
mailmap['badariprasad.h@gmail.com']  = '919686111887@inbound.edulead.in'
mailmap['badari.hp@outlook.com']     = "919845837392@inbound.edulead.in"
mailmap['badari.ph@gmail.com']       = "badari.hp@inbound.edulead.in"
mailmap['harish.v.murthy@gmail.com'] = '919035295469@inbound.edulead.in'
mailmap['badari.hp@gmail.com']       = 'testingmail@inbound.edulead.in'

def isourdomain(a):
  domain = a.split('@')
  if domain[-1] == OUR_DOMAIN:
    return True
  return False

def getmapaddr(a,rev=False):
  if isourdomain(a):
    if rev:
      return mailmap[a]
    return a
  if not a in mailmap:
    mapped = base64.urlsafe_b64encode(str(uuid.uuid4()).encode()).decode('ascii')+'@'+OUR_DOMAIN
    mailmap[a] = mapped
    mailmap[mapped] = a
  return mailmap[a]

def mapaddrlist(li):
  rli = []
  for x in li:
    if x[1]:
      rli.append(email.utils.formataddr((x[1],getmapaddr(x[0]))))
    else:
      rli.append(x[0])
  return rli

def populate_from_addresses(ev, msg):
    msg['From'] = email.utils.formataddr((ev['msg']['from_name'], getmapaddr(ev['msg']['from_email'])))

def updateAttachments(ev, msg, keys):
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

def updatemail(ev, msg, keys):
    msg['Subject'] = ev['msg']['subject'] + "TESTING 2"
    text = ev['msg']['text']
    html = ev['msg']['html']
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(html, 'html')
    msg.attach(part1)
    msg.attach(part2)

    updateAttachments(ev, msg, keys)

def sendmail(ev, msg, to):
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

    print ('RCPT : {}'.format(to))

    composed = msg.as_string()
    print ("ACTUAL MSG \n {} \n".format(composed))
    server.sendmail(ev['msg']['from_email'], to, composed)
  finally:
    server.quit()

def decode_mail(ev):
  if ev['msg']['spam_report']['score'] >= 5:
    print('Spam!!')
  else:
    msg = MIMEMultipart('alternative')
    updatemail(ev, msg, keys)
    msg['X-MC-PreserveRecipients'] = 'true'
    populate_from_addresses(ev, msg)
    msg.add_header("Message-Id", ev['msg']['headers']['Message-Id'])
    msg.add_header("In-Reply-To", ev['msg']['headers']['In-Reply-To'])
    msg.add_header("References", ev['msg']['headers']['References'])

    allrecipients = ev['msg']['to']
    if 'cc' in ev['msg']:
      allrecipients = allrecipients + ev['msg']['cc']
    for mailid in allrecipients:
      if not isourdomain(mailid[0]):
        continue
      rto = mapaddrlist(allrecipients)
      rto.remove(mailid[0])
      msg['To'] = ','.join(rto)
      if mailid[1]:
        recepient = email.utils.formataddr(mailid[1],getmapaddr(mailid[0],True))
      else:
        recepient = getmapaddr(mailid[0],True)
      sendmail(ev, msg, recepient)


if __name__=="__main__":
  if (len(sys.argv) <= 1):
    raise ValueError("Script expects filename as arg")
  else:
    with open(sys.argv[1],'r') as f:
      records = json.load(f)
      for line in records:
        for keys in line:
          if isinstance(line[keys], dict) and keys == 'msg':
            decode_mail(line)
          else:
            continue
        print ("\n\n==============================\n")

