#! /usr/bin/python3.4
import configparser
import os

config_file = 'readdress_config.ini'

class ReConfig:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.optionxform = str
        self.config_file = os.path.join(os.getcwd(), config_file)
        if not os.path.isfile(self.config_file):
            raise ValueError("MISSING Config file {}".format(config_file))

        try :
            print ("Reading config file {}".format(self.config_file))
            self.config.read( self.config_file )
        except:
            raise
        return

    def ConfigSectionMap(self, section):
        print ("Sections : {}".format(self.config.sections()))
        if section == 'DEFAULT':
            return self.config.defaults()

        if section in self.config:
            return self.config[section]
        else:
            raise ValueError("Config Some thing worng for section {}".format(section))

    def get_ourdomain(self):
        return self.config.defaults().get('OUR_DOMAIN',None)
    
    def get_redis_mail_dump_exp_time(self):
        return int (self.config.defaults().get('REDIS_MAIL_DUMP_EXPIRY_TIME', '600') )

    def get_sendmail_key_exp_time(self):
        return int (self.config.defaults().get('SENDMAIL_KEY_EXPIRE_TIME', '300') )

    def get_noreply_name(self):
        return self.config.defaults().get('NOREPLY_NAME', None)

    def get_noreply_mailid(self):
        return self.config.defaults().get('NOREPLY_ADDRESS', None)

    def get_formatted_noreply(self):
        import email.utils
        return email.utils.formataddr( ( self.get_noreply_name(), self.get_noreply_mailid() ))
