import tornado.ioloop
import tornado.web
import json
import sys
from tornado.log import logging, gen_log

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("Hello, world")

class RecvHandler(tornado.web.RequestHandler):
  def post(self):
    gen_log.info('inbound recv hit!')
    ev = self.get_argument('mandrill_events',False)
    if not ev:
      pass
    else:
      gen_log.info('mandrill_events ' + str(ev))
      jev = json.loads(ev, "utf-8")
      if jev[0]['msg']['spam_report']['score'] >= 5:
        print('Spam!!')
      else:
        print('subject: ' + jev[0]['msg']['subject'])
        print('text part: ' + jev[0]['msg']['text'])
        print('html part: ' + jev[0]['msg']['html'])
        print('from: ' + jev[0]['msg']['from_email'])
        print('From: ' + jev[0]['msg']['from_name'])
        print("===================================================================")
        print('Headers: ' , jev[0]['msg']['headers'])
        print("===================================================================")

        for to,toname in jev[0]['msg']['to']:
          print('to: ' + to)
          if toname:
            print('To: ' + toname)

        if 'attachments' in jev[0]['msg']:
          for name,attachment in jev[0]['msg']['attachments'].items():
            print('attachmet name ' + attachment['name'])
            print('attachmet type ' + attachment['type'])
            print('attachmet base64 ' + attachment['base64'])

        if 'images' in jev[0]['msg']:
          for name,image in jev[0]['msg']['images'].items():
            print('image name ' + image['name'])
            print('image type ' + image['type'])
            print('image base64 ' + image['base64'])

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

application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/recv", RecvHandler),
])

if __name__ == "__main__":
    application.listen(8985)
    tornado.ioloop.IOLoop.current().start()
