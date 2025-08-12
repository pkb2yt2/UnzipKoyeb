# In unzipbot/helpers/gofile_helper.py

import aiohttp
import re
import logging

LOGGER = logging.getLogger(__name__)

async def resolve_gofile_link(url: str):
    """
    Resolves a Gofile link by creating a guest account to get a token,
    and then returns a dictionary with the direct link and the required Cookie header.
    """
    async with aiohttp.ClientSession() as session:
        try:
            LOGGER.info("Gofile: Creating guest account to get API token.")
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"}
            async with session.post("https://api.gofile.io/accounts", headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    return None, f"Gofile Error: Could not create a guest session (Status: {resp.status})."
                json_data = await resp.json()
                if json_data.get("status") != "ok":
                    return None, "Gofile Error: Could not get a guest token."
                token = json_data["data"]["token"]
                LOGGER.info("Gofile: Successfully retrieved guest token.")
        except Exception as e:
            return None, f"Gofile Error: An error occurred during session creation: {e}"

        try:
            content_id = re.findall(r"gofile\.io/(?:d|f)/([A-Za-z0-9]+)", url)[0]
        except IndexError:
            return None, "Invalid Gofile URL format."

        api_url = f"https://api.gofile.io/contents/{content_id}?wt=4fd6sg89d7s6&cache=true"
        api_headers = {"Authorization": f"Bearer {token}"}

        try:
            async with session.get(api_url, headers=api_headers, timeout=15) as resp:
                if resp.status != 200:
                    return None, f"Gofile API Error (Status: {resp.status})."
                j = await resp.json()
                if j.get("status") == "ok":
                    data = j.get("data", {})
                    link = None
                    if data.get("type") == "folder":
                        children = data.get("children", {})
                        for child_data in children.values():
                            if child_data.get("type") == "file" and "link" in child_data:
                                link = child_data["link"]
                                break
                    elif "link" in data:
                        link = data["link"]

                    if link:
                        # Return a dictionary with the link and the crucial header
                        headers_list = [f"Cookie: accountToken={token}"]
                        return {"url": link, "headers": headers_list}, None
                    
                    return None, "Gofile Error: No link found in API response."
                else:
                    return None, f"Gofile API Error: {j.get('data', {}).get('message', 'Unknown error')}"
        except Exception as e:
            return None, f"An unexpected error occurred during the API call: {e}"