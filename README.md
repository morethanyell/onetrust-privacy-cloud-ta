# OneTrust Privacy Cloud Splunk TA
Collects OneTrust Privacy Cloud Requests (DSAR) JSON data. This Splunk TA houses a modular input or a script that utilizes OneTrust API for "Get All Requests" under the [OneTrust Privacy Cloud - Privacy Rights Automation](https://developer.onetrust.com/onetrust/reference/getallrequestqueuesv2usingget).

## Installation Guide
Install the latest version from [Splunkbase](https://splunkbase.splunk.com/app/6741) or download the app's full directory in the `src` folder in this repository: `TA-onetrust_privacy_cloud`. Once the app is installed in your Splunk Enterprise environment, restart the Splunk daemon. Confirm the installation by checking the availability of the modular input, e.g.:

```
SplunkWeb GUI > Settings > Data Inputs > OneTrust Privacy Cloud
```

## Configuring a collection
To configure a collection, you will need two things:
- The domain of the environment, i.e. `hostname` e.g. `https://trial.onetrust.com`
- The OAuth2 Bearer Token
#### Steps
1. As user with admin role, login on to your Splunk Environment
2. Navigate to Settings > Data Inputs > OneTrust Privacy Cloud
3. Click `New`
4. You should be able to see the form for `OneTrust Privacy Cloud Token Credentials`
    - Give your input a unique name under the `name` textbox (must not contain spaces)
    - Enter the domain of the environment or the hostname. Start with `https` and end with `.com`. Do not end with a forward slash `/`. E.g.: `https://trial.onetrust.com`
    - Enter your OAuth2 Bearer Token under the `API Token` textbox
    - Enter the date from when you wanted to start collecting. It is important to follow the format `yyyymmdd`
5. Click `More settings`
6. Under `Interval` enter a valid Cron schedule or interval in seconds
    - It is suggested to use interval in seconds and the value of a minimum of 3600 (collect every 30 minutes)
7. Leave `Set sourcetype` as `Automatic`
8. Enter your preferred host under the `Host` textbox
    - We recommend that you enter here the same value as the one you use `hostname`
9. Set your index under the `index` dropdown* menu
10. Finally, enable your input as it is disabled by default

*If you're configuring this on a Splunk Heavy Forwarder that is not aware of the list of indexes available in your Indexer Cluster (e.g.: SplunkCloud), just select `default` for Step 9. Once done, directly modify the `inputs.conf` using your favorite text editor. Under the stanza `[onetrust_privacy_cloud://<name you gave>]`, look for `index = default` and then replace the value to your chosen index.

### Troubleshooting
Check for internal logs by running the SPL below:

```
index=_internal source=*splunkd.log "onetrust_privacy_cloud.py" 
| transaction thread_id source maxspan=<the value you enter for Step 6> startswith="New scheduled exec process" endswith="Streaming OneTrust Privacy Cloud has been successful"
```
##### Buy me a beer: paypal.me/morethanyell