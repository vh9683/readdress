#!/usr/bin/python3.4
import re
import json
import sys
import smtplib
import tempfile
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
import uuid
import base64


indent = 1
'''
def print_dict(dic, name):
    print ("DICTONARY : {} -->".format(name))
    space ='|'
    print ('++++++++++++++++++++++++++++++++++++++++++++++++++++\n')
    global indent

    for i in range(indent):
        space += '- '

    for i in dic:
        if not isinstance(dic[i], dict):
            print ('{} keys[{}]                :  {}\n'.format(space, i, dic[i]))
        else:
            print_dict(dic[i], i)
    print ('++++++++++++++++++++++++++++++++++++++++++++++++++++\n')
    indent += 1
'''

mapper = dict()
mapper['9686111887@inbound.edulead.in'] = 'badariprasad.h@gmail.com'
mapper["9845837392@inbound.edulead.in"] = 'badari.hp@outlook.com'
mapper["badari.hp@inbound.edulead.in"]  = 'badari.ph@gmail.com'
mapper['harish@inbound.edulead.in']     = 'harish.v.murthy@gmail.com'
mapper['testingmail@inbound.edulead.in']= 'badari.hp@gmail.com'

reversemap = dict()
reversemap['badariprasad.h@gmail.com']  = '9686111887@inbound.edulead.in'
reversemap['badari.hp@outlook.com']     = "9845837392@inbound.edulead.in"
reversemap['badari.ph@gmail.com']       = "badari.hp@inbound.edulead.in"
reversemap['harish.v.murthy@gmail.com'] = 'harish@inbound.edulead.in'
reversemap['badari.hp@gmail.com']       = 'testingmail@inbound.edulead.in'


def lookup(email):
  mappedmail =  mapper.get(email) 
  return mappedmail

def getpsuedomail(email):
  mappedmail =  reversemap.get(email) 
  return mappedmail

def populate_from_addresses(ev, msg, keys):
    isreplymail = False
    #msg['From'] = email.utils.formataddr((ev['msg']['from_name'], ev['msg']['from_email']))
    if 'inbound' in ev['msg']['from_email']:
        msg['From'] = email.utils.formataddr((ev['msg']['from_name'], ev['msg']['from_email']))
        isreplymail = True
    else:
        emailaddress = getpsuedomail(ev['msg']['from_email'])
        msg['From'] = email.utils.formataddr((ev['msg']['from_name'], emailaddress))
    
    return isreplymail

def populate_to_addresses(ev, msg, keys):
    rcptslist = list()
    actuallist = list()
    #toaddresses =""
    if 'to' in keys:
      for to,toname in ev['msg']['to']:
        #print('to: ' + to)
        mto = ""
        if 'inbound' in to :
          mto = lookup(to)
        else:
          mto = getpsuedomail(to)

        if mto is None:
           mto = to

        if toname:
            #toaddresses += email.utils.formataddr((toname,to)) + ' ,'
            actuallist.append(email.utils.formataddr((toname,to)))
        else:
            #toaddresses += to + ' ,'
            actuallist.append(to)

        rcptslist.append(mto)

    #msg['To'] = toaddresses + 'testingloop@inbound.edulead.in'
    return rcptslist, actuallist

def populate_cc_addresses(ev, msg, keys):
    rcptslist = list()
    actuallist = list()
    ccaddresses = ""
    if 'cc' in keys:
      for cc,ccname in ev['msg']['cc']:
        mcc = ""
        if 'inbound' in cc :
          mcc = lookup(cc)
        else:
          mcc = getpsuedomail(cc)

        if mcc is None:
           mcc = cc

        if ccname:
            ccaddresses = email.utils.formataddr((ccname,cc)) + ','
            actuallist.append(email.utils.formataddr((ccname,cc)))
        else:
            ccaddresses += cc + ','
            actuallist.append(cc)
        rcptslist.append(mcc)

    #msg['Cc'] = ccaddresses

    ''' 
    bccmail = list()
    if bccmightbepresent:
        msg['X-MC-PreserveRecipients'] = 'false'
        recvdlist = (ev['msg']['headers']['Received'])
        for i in recvdlist:
            match = re.search('([\w.-]+)@([\w.-]+)', i)
            if match is not None:
                bccemail = match.group()
                if 'edulead' in bccemail and 'from' in i:
                    bccmail.append(bccemail)
        setaddr = set(bccmail)
        bccmail = list(setaddr)
        rcptslist.append(bccmail)
        msg['Bcc'] = ','.join(bccmail)
    '''

    return rcptslist, actuallist

def decode_mail(ev):
  print ("TYPE EV : {}".format(type(ev)))
  if ev['msg']['spam_report']['score'] >= 5:
    print('Spam!!')
  else:
    print("*********************************************************\n")
    print('subject: ' + ev['msg']['subject'])
    print('text part: ' + ev['msg']['text'])
    print('html part: ' + ev['msg']['html'])
    print('from: ' + ev['msg']['from_email'])
    print('From: ' + ev['msg']['from_name'])
    keys = [ k for k in ev['msg'] if k in ev['msg'].keys() ]
    values = [ k for k in ev['msg'] if k in ev['msg'].values() ]
    print ("Keys {}".format(keys))
    print ("Type of keys : {}".format(type(ev['msg'])))
    print("*********************************************************\n")
    
    '''
    print ("------------------------------------------\n")
    for k in ev:
        print ('1 keys[{}]                :  {}\n'.format(k[0], k[1]))
        if isinstance(ev[k], dict):
            print ("------\n")
            dic = ev[k]
            print_dict(dic, k)
            print ("------\n")
            
    print ("------------------------------------------\n")
    '''
    
    msg = MIMEMultipart('alternative')
    updatemail(ev, msg, keys)
    msg['X-MC-PreserveRecipients'] = 'true'
    populate_from_addresses(ev, msg, keys)
    torcpts, toactuallist = populate_to_addresses(ev, msg, keys)
    msg['Comments'] = ','.join(torcpts)
    msg['Keywords'] = ','.join(torcpts)
    msg['X-MC-Metadata'] = '{ "trans_id": "123" }'
    ccrcpts,ccactuallist = populate_cc_addresses(ev, msg, keys)
    #rcptslist = torcpts + ccrcpts 
    print ("TO : {}".format(torcpts))
    print ("ATO : {}".format(toactuallist))

    REPLY_TO_ADDRESS = base64.urlsafe_b64encode(str(uuid.uuid4()).encode()).decode('ascii')
    REPLY_TO_ADDRESS = REPLY_TO_ADDRESS + '@inbound.edulead.in'
    print('REPLY_TO_ADDRESS : {}'.format(REPLY_TO_ADDRESS))
    msg.add_header("Message-Id", REPLY_TO_ADDRESS)

    allrecipients = torcpts + ccrcpts
    print('\n')
    for mailid in allrecipients:
        arcpts = list(allrecipients)
        todup = list(toactuallist)
        ccdup = list(ccactuallist)
        mailidx = torcpts.index(mailid)
        print ("mailidx : {}".format(mailidx))
        toremovemail = todup[mailidx]
        print ("to recipient : {} toremovemail: {}".format(mailid, toremovemail))
        if toremovemail is not None:
            todup.remove(toremovemail)
        elif ccdup is not None:
            ccremovemail = ccdup[mailidx]
            print ("ccrcpt : {} cremovemail :{}".format(mailid, ccremovemail))
            ccdup.remove(ccremovemail)
            
        toremovemail = None
        ccremovemail = None
        toheaders = ','.join(todup) 
        ccheaders = '.'.join(ccdup)

        print("To Header: {}".format(toheaders))
        print("CC Header: {}".format(ccheaders))
        
        actualmsg = None
        actualmsg = msg
        actualmsg['To'] = toheaders
        actualmsg['Cc'] = ccheaders

        sendmail(ev, actualmsg, mailid)
        #del actualmsg['Message-Id'] 
        #del actualmsg['To'] 
        #del actualmsg['Cc'] 
        del msg['To'] 
        del msg['Cc'] 
        del actualmsg
        del todup 
        del ccdup 
        del toheaders, ccheaders 
        print ("sent mail successfully")

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
    print ("Tryingin to send mail\n")
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

if __name__ == "__main__":
    if (len(sys.argv) <= 1):
        raise ValueError("Script expects filename as arg")
    else:
        with open(sys.argv[1],'r') as f:
            records = json.load(f)
            for line in records:
                print("Data type line: {}".format(type(line)) )
                for keys in line:
                    print ("Type of {} :  {} ".format(keys, type( line[keys])) )
                    if isinstance(line[keys], dict) and keys == 'msg':
                        print ("Keys : {} , Values :  {} ".format(keys, "DICTONARY"))
                        decode_mail(line)
                    else:
                        print ("Keys : {} , Values :  {} ".format(keys, line[keys]))
                print ("\n\n==============================\n")
