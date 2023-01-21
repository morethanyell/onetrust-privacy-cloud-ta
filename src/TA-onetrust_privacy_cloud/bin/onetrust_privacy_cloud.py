import json
import os
import sys
import requests
import socket
import time
from datetime import datetime
from splunklib.modularinput import *
import splunklib.client as client

class OneTrustPrivacy(Script):
    
    MASK = "***ENCRYPTED***"
    NO_JSON_DATA = "n/a"
    CHECKPOINT_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tmp', 'CHECKPOINT'))
    
    def get_scheme(self):
        scheme = Scheme("OneTrust Privacy Cloud")
        scheme.use_external_validation = False
        scheme.use_single_instance = False
        scheme.description = "OneTrust Privacy Cloud Token Credentials"

        base_url = Argument("base_url")
        base_url.title = "URL"
        base_url.data_type = Argument.data_type_string
        base_url.description = "E.g. https://customer.my.onetrust.com"
        base_url.required_on_create = True
        base_url.required_on_edit = False
        scheme.add_argument(base_url)
        
        api_token = Argument("api_token")
        api_token.title = "API Token"
        api_token.data_type = Argument.data_type_string
        api_token.description = "OAuth2 Bearer Token"
        api_token.required_on_create = True
        api_token.required_on_edit = False
        scheme.add_argument(api_token)
        
        start_date = Argument("start_date")
        start_date.title = "Start Date"
        start_date.data_type = Argument.data_type_string
        start_date.description = "Use the format yyyymmdd. Default is 1 week ago."
        start_date.required_on_create = True
        start_date.required_on_edit = False
        scheme.add_argument(start_date)
        
        return scheme
    
    def validate_input(self, definition):
        pass
    
    def encrypt_keys(self, _base_url, _api_token, _session_key):

        args = {'token': _session_key}
        service = client.connect(**args)

        credentials = {"baseUrl": _base_url, "apiToken": _api_token}

        try:
            for storage_password in service.storage_passwords:
                if storage_password.username == _base_url:
                    service.storage_passwords.delete(username=storage_password.username)
                    break

            service.storage_passwords.create(json.dumps(credentials), _base_url)

        except Exception as e:
            raise Exception("Error encrypting: %s" % str(e))
    
    def decrypt_keys(self, _base_url, _session_key):

        args = {'token': _session_key}
        service = client.connect(**args)

        for storage_password in service.storage_passwords:
            if storage_password.username == _base_url:
                return storage_password.content.clear_password

    def mask_credentials(self, _base_url, _api_token, _input_name, _session_key):

        try:
            args = {"token": _session_key}
            service = client.connect(**args)

            kind, _input_name = _input_name.split("://")
            item = service.inputs.__getitem__((_input_name, kind))

            kwargs = {
                "base_url": _base_url,
                "api_token": self.MASK
            }

            item.update(**kwargs).refresh()

        except Exception as e:
            raise Exception("Error updating inputs.conf: %s" % str(e))
    
    def get_all_request(self, ew, _base_url, _api_token, _checkpoint, _page):
        
        url = f"{_base_url}/api/datasubject/v2/requestqueues/en-us?&modifieddate={_checkpoint}&page={_page}&size=500&sort=asc"

        ew.log("INFO", f"OneTrust API Call: GET {url}")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_token}"
        }

        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                ew.log("ERROR", f"API call returned request_status_code={str(response.status_code)}. Failed to retrieve Privacy Cloud Request from {_base_url}.")
                sys.exit(1)
            
            return response.json()
        except Exception as e:
            ew.log("ERROR", f"Error retrieving Privacy Cloud Requests from page={str(_page)}. err_msg=\"{str(e)}\"")
            sys.exit(1)

    def update_checkpoint(self, _chkpt):
        
        with open(self.CHECKPOINT_FILE_PATH, 'w+') as f:
            f.write(f'{_chkpt}\n')
            f.close()
    
    def read_checkpoint(self, ew):
        
        if not os.path.exists(self.CHECKPOINT_FILE_PATH):
            
            ew.log("INFO", f'Expected checkpoint file is not found. Creating new a one: {self.CHECKPOINT_FILE_PATH}')
            
            with open(self.CHECKPOINT_FILE_PATH, "w+") as f:
                f.write("")
                f.close()
            
            ew.log("INFO", f'New checkpoint file has been successfully created.')
        
        with open(self.CHECKPOINT_FILE_PATH, 'r') as f:
            fcontents = f.readlines()
            f.close()
        
        retval = -1
        
        if fcontents is None:
            return retval
        
        if len(fcontents) < 1:
            return retval
        
        try:
            retval = int(fcontents[-1])
            return retval
        except ValueError:
            return retval
            
    def format_mepoch(self, checkpoint_cur):
        return datetime.fromtimestamp(checkpoint_cur / 1000).strftime(f"%FT%X.%f")[:-3] + " UTC"

    def parse_datestr(self, ew, datestr):
        date_obj = datetime.strptime(datestr, f"%Y-%m-%dT%H:%M:%S.%fZ")
        millis = str(date_obj)[20:23]
        return int(date_obj.strftime("%s") + millis)

    def stream_events(self, inputs, ew):
        
        start = time.time()

        self.input_name, self.input_items = inputs.inputs.popitem()
        session_key = self._input_definition.metadata["session_key"]

        base_url = str(self.input_items["base_url"]).strip()
        api_token = str(self.input_items["api_token"]).strip()
        checkpoint = str(self.input_items["start_date"]).strip()
        checkpoint_meta = int(datetime.strptime(f"{checkpoint}000000", f"%Y%m%d%H%M%S").strftime("%s")) 
        checkpoint_meta = checkpoint_meta * 1000
        total_events_written = 0
        total_events_skipped = 0
        
        if base_url[-1] == '/':
            base_url = base_url.rstrip(base_url[-1])
        
        try:
            if api_token != self.MASK:
                self.encrypt_keys(base_url, api_token, session_key)
                self.mask_credentials(base_url, api_token, self.input_name, session_key)

            decrypted = self.decrypt_keys(base_url, session_key)
            self.CREDENTIALS = json.loads(decrypted)
            api_token = str(self.CREDENTIALS["apiToken"]).strip()
            
            ew.log("INFO", f"API credentials and other parameters retrieved.")

            # Assumes there at least 1 page
            req_ids_pages = 1
            page_flipper = 0
            apiScriptHost = socket.gethostname()
            checkpoint_cur = self.read_checkpoint(ew)
            
            if checkpoint_cur < 0 :
                self.update_checkpoint(checkpoint_meta)
                checkpoint_cur = checkpoint_meta
                ew.log("INFO", f"Looks like this is a start of a new collection so we're using the 'Start Date' as initial checkpoint: {self.format_mepoch(checkpoint_cur)}.")
            
            ew.log("INFO", f"Streaming OneTrust Privacy Cloud Requests from base_url={base_url}. Current checkpoint: {self.format_mepoch(checkpoint_cur)}.")
            
            # For API parameter, get the latest Checkpoint rather than the one saved in inputs stanza
            api_start_date = datetime.fromtimestamp(checkpoint_cur / 1000).strftime(f"%Y%m%d")
            max_date_updated = 0
            
            while page_flipper < req_ids_pages:
                
                req_ids_curpage = self.get_all_request(ew, base_url, api_token, api_start_date, page_flipper)
                
                # At first iteration, get the total number of pages
                if page_flipper == 0:
                    if "totalPages" in req_ids_curpage:
                        req_ids_pages = req_ids_curpage["totalPages"]
                
                if "content" not in req_ids_curpage:
                    continue
                
                # Streaming all Assessment Summaries first
                for reqItem in req_ids_curpage["content"]:
                    
                    # Retrieve Mepoch from the JSON resp and convert to millis
                    date_updated = self.parse_datestr(ew, reqItem["dateUpdated"])
                    
                    if date_updated > max_date_updated:
                        max_date_updated = date_updated
                    
                    # Ignore this iteration and EventWriting if checkpoint is larger than the dateUpdated 
                    if checkpoint_cur > date_updated :
                        total_events_skipped = total_events_skipped + 1
                        continue
                    
                    reqItem["tenantHostname"] = base_url
                    reqItem["apiPage"] = page_flipper
                    reqItem["apiScriptHost"] = apiScriptHost
                    reqItemEvent = Event()
                    reqItemEvent.stanza = self.input_name
                    reqItemEvent.sourceType  = "onetrust:privacy:requests"
                    reqItemEvent.data = json.dumps(reqItem)
                    ew.write_event(reqItemEvent)
                    total_events_written = total_events_written + 1
                
                page_flipper += 1
            
            ew.log("INFO", f"Updating checkpoint date to: {self.format_mepoch(max_date_updated)} (epoch_millis={str(max_date_updated)})")
            self.update_checkpoint(max_date_updated)
            
        except Exception as e:
            ew.log("ERROR", f"Error streaming events: err_msg=\"{str(e)}\"")
            
        end = time.time()
        elapsed = round((end - start) * 1000, 2)
        ew.log("INFO", f"Streaming OneTrust Privacy Cloud has been successful / completed in {str(elapsed)} ms. Total events ingested: {str(total_events_written)}. Total events skipped due to checkpoint: {str(total_events_skipped)}.")

if __name__ == "__main__":
    sys.exit(OneTrustPrivacy().run(sys.argv))