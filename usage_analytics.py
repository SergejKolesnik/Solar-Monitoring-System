"""Optional anonymous page-view tracking for the public Streamlit app."""

from __future__ import annotations

import json

import streamlit.components.v1 as components

from runtime_config import get_secret


def capture_anonymous_pageview() -> None:
    """Capture one anonymous page view when PostHog is configured."""

    api_key = get_secret("POSTHOG_API_KEY")
    if not api_key:
        return

    host = str(get_secret("POSTHOG_HOST", "https://eu.i.posthog.com")).rstrip("/")
    api_key_json = json.dumps(str(api_key))
    host_json = json.dumps(host)

    components.html(
        f"""
        <script>
        (function () {{
          if (window.__skygridUsageTracked) return;
          window.__skygridUsageTracked = true;
          !function(t,e){{var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){{function g(t,e){{var o=e.split('.');2==o.length&&(t=t[o[0]],e=e[1]),t[e]=function(){{t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}}}(p=t.createElement('script')).type='text/javascript',p.async=!0,p.src=s.api_host.replace('.i.posthog.com','-assets.i.posthog.com')+'/static/array.js',(r=t.getElementsByTagName('script')[0]).parentNode.insertBefore(p,r);var u=e;void 0!==a?u=e[a]=[]:a='posthog',u.people=u.people||[],u.toString=function(t){{var e='posthog';return'posthog'!==a&&(e+='.'+a),t||(e+=' (stub)')}},u.people.toString=function(){{return u.toString(1)+' (stub)'}},o='capture identify alias people.set people.set_once reset groups register register_once unregister opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing'.split(' ');for(n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])}},e.__SV=1)}}(document,window.posthog||[]);
          posthog.init({api_key_json}, {{api_host:{host_json}, autocapture:false, disable_session_recording:true, person_profiles:'never'}});
          posthog.capture('$pageview', {{app_name:'skygrid-solar', $current_url:window.parent.location.href, $process_person_profile:false}});
        }})();
        </script>
        """,
        height=0,
        width=0,
    )
