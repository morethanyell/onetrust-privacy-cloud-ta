import json
import os
import sys
import requests
import hashlib
import socket
import re
import time
from splunklib.modularinput import *
import splunklib.client as client

class OneTrustPrivacy(Script):
    
    MASK = "***ENCRYPTED***"
    NO_JSON_DATA = "n/a"
    
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
        
        url = f"{_base_url}/api/datasubject/v2/requestqueues/en-us?&modifieddate={_checkpoint}&page={_page}&size=500&sort=desc"

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

    def stream_events(self, inputs, ew):
        
        start = time.time()

        self.input_name, self.input_items = inputs.inputs.popitem()
        session_key = self._input_definition.metadata["session_key"]

        base_url = str(self.input_items["base_url"]).strip()
        api_token = str(self.input_items["api_token"]).strip()
        checkpoint = str(self.input_items["start_date"]).strip()
        
        if base_url[-1] == '/':
            base_url = base_url.rstrip(base_url[-1])
        
        ew.log("INFO", f"Streaming OneTrust Privacy Cloud Requests from base_url={base_url}. Starting on {checkpoint}")

        try:
            if api_token != self.MASK:
                self.encrypt_keys(base_url, api_token, session_key)
                self.mask_credentials(base_url, api_token, self.input_name, session_key)

            decrypted = self.decrypt_keys(base_url, session_key)
            self.CREDENTIALS = json.loads(decrypted)
            api_token = str(self.CREDENTIALS["apiToken"]).strip()

            # Assumes there at least 1 page
            req_ids_pages = 1
            page_flipper = 0
            apiScriptHost = socket.gethostname()

            ew.log("INFO", f"API credentials and other parameters retrieved.")
                        
            while page_flipper < req_ids_pages:
                
                req_ids_curpage = self.get_all_request(ew, base_url, api_token, checkpoint, page_flipper)

                # At first iteration, get the total number of pages
                if page_flipper == 0:
                    if "totalPages" in req_ids_curpage:
                        req_ids_pages = req_ids_curpage["totalPages"]
                
                if "content" not in req_ids_curpage:
                    continue
                
                # Streaming all Assessment Summaries first
                for reqItem in req_ids_curpage["content"]:
                    reqItem["tenantHostname"] = base_url
                    reqItem["apiPage"] = page_flipper
                    reqItem["apiScriptHost"] = apiScriptHost
                    reqItemEvent = Event()
                    reqItemEvent.stanza = self.input_name
                    reqItemEvent.sourceType  = "onetrust:privacy:requests"
                    reqItemEvent.data = json.dumps(reqItem)
                    ew.write_event(reqItemEvent)
                
                page_flipper += 1

        except Exception as e:
            ew.log("ERROR", f"Error streaming events: err_msg=\"{str(e)}\"")
            
        end = time.time()
        elapsed = round((end - start) * 1000, 2)
        ew.log("INFO", f"Streaming OneTrust Privacy Cloud has been successful / completed in {str(elapsed)} ms.")

if __name__ == "__main__":
    sys.exit(OneTrustPrivacy().run(sys.argv))