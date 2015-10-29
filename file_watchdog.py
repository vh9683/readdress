import sys
import time
from watchdog.observers import Observer
from watchdog.events import LoggingEventHandler
import logging
import logging.handlers

handler='FILEWATCHDOG-['+instance+']'
formatter = ('\n'+handler+':%(asctime)s-[%(filename)s:%(lineno)s]-%(levelname)s - %(message)s')
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=formatter)
logger = logging.getLogger('watchdog')

rclient = StrictRedis()

class logevent(LoggingEventHandler):
    """Logs all the events captured."""

    def publish_cfg_modified(self, what, filepath):
        basename = os.path.basename(filepath)
        if what == 'file' and basename == 'readdress_config.ini':
            msg = "CFG MODIFIED"
            count = rclient.publish('configmodified', msg)
            logger.info('message published to ' + str(count))
        return
        

    def on_moved(self, event):
        super(logevent, self).on_moved(event)
        what = 'directory' if event.is_directory else 'file'
        logging.info(" Moved %s: from %s to %s", what, event.src_path,
                     event.dest_path)
        self.publish_cfg_modified()

    def on_created(self, event):
        super(logevent, self).on_created(event)
        what = 'directory' if event.is_directory else 'file'
        logging.info(" Created %s: %s", what, event.src_path)
        self.publish_cfg_modified()

    def on_deleted(self, event):
        super(logevent, self).on_deleted(event)
        what = 'directory' if event.is_directory else 'file'
        logging.info(" Deleted %s: %s", what, event.src_path)
        self.publish_cfg_modified()

    def on_modified(self, event):
        super(logevent, self).on_modified(event)
        what = 'directory' if event.is_directory else 'file'
        logging.info(" Modified %s: %s", what, event.src_path)
        self.publish_cfg_modified()
   

if __name__ == "__main__":
    path = sys.argv[1]
    event_handler = logevent()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
