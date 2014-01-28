# Foris - web administration interface for OpenWrt based on NETCONF
# Copyright (C) 2013 CZ.NIC, z.s.p.o. <http://www.nic.cz>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import urlparse

import bottle
from functools import wraps
import logging
from xml.etree import cElementTree as ET


logger = logging.getLogger("foris.utils")


def redirect_unauthenticated(redirect_url=None):
    redirect_url = redirect_url or "/"
    session = bottle.request.environ['beaker.session']
    no_auth = bottle.default_app().config.no_auth
    if not no_auth and not session.get("user_authenticated", False):
        # "raise" bottle redirect
        bottle.redirect("%s?next=%s" % (redirect_url, bottle.request.fullpath))


def login_required(func=None, redirect_url=None):
    """Decorator for views that require login.

    :param redirect_url:
    :return:
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        redirect_unauthenticated(redirect_url)
        return func(*args, **kwargs)
    return wrapper


def is_safe_redirect(url, host=None):
    """
    Checks if the redirect URL is safe, i.e. it uses HTTP(S) scheme
    and points to the host specified.

    Also checks for presence of newlines to avoid CRLF injection.

    :param url: URL to check
    :param host: host that has to match the URL's host, if specified
    :return:
    """
    if "\r" in url or "\n" in url:
        logger.warning("Possible CRLF injection attempt: \n%s" % bottle.request.environ)
        return False
    url_components = urlparse.urlparse(url)
    logger.info(url_components)
    logger.info(host)
    return ((not url_components.scheme or url_components.scheme in ['http', 'https'])
            and (not url_components.netloc or url_components.netloc == host))




class Lazy(object):
    def __init__(self, func):
        self.func = func
        self.value = None

    def __call__(self):
        if self.value is None:
            self.value = self.func()
        return self.value

    def __getattr__(self, item):
        if self.value is None:
            self.value = self.func()
        return getattr(self.value, item)


def print_model(model):
    import copy
    toprint = copy.deepcopy(model.get_tree())
    indent(toprint)
    data = ET.tostring(toprint)
    logger.debug(data)
    return data


def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for e in elem:
            indent(e, level+1)
        if not e.tail or not e.tail.strip():
            e.tail = i
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = i