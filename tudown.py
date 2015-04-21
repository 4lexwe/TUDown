#!/usr/bin/python3
from threading import Thread
import threading
from requests import Session, utils
from lxml import html
from re import compile, findall
from os import makedirs
from os.path import exists, getmtime
from calendar import timegm
from time import strptime, clock, time, sleep

NUM_THREADS = 5  # It's ok....

def create_filepath(filepath):
    if not exists(filepath):
        makedirs(filepath)


def download_files(session, f):
    filename = f[1] + utils.unquote(f[0])[utils.unquote(f[0]).rindex('/'):]
    if not exists(filename):
        response = session.get(f[0])
        if response.status_code == 200:
            create_filepath(f[1])
            with open(filename, 'wb') as fd:
                for chunk in response.iter_content(1024):
                    fd.write(chunk)
            print('[+] ' + filename)
    else:
        response = session.head(f[0])
        if response.status_code == 200:
            last_mod_file = getmtime(filename)
            last_mod_www = timegm(strptime(response.headers['Last-Modified'], '%a, %d %b %Y %H:%M:%S %Z'))
            if last_mod_www > last_mod_file:
                response = session.get(f[0])
                if response.status_code == 200:
                    create_filepath(f[1])
                    with open(filename, 'wb') as fd:
                        for chunk in response.iter_content(1024):
                            fd.write(chunk)
                    print('[M] ' + filename)


def resolve_direct_links(session, hrefs):
    links = []
    t = clock()
    for href in hrefs:
        tmp = session.head(href).headers
        if 'Location' in tmp:
            links.append(tmp['Location'])
    #print("delta resolve:", clock() - t)
    return links


def get_links_from_folder(session, urls):
    hrefs = []
    t = clock()
    for url in urls:
        response = session.get(url)
        hrefs += findall(compile(
            'https\:\/\/www\.moodle\.tum\.de\/pluginfile\.php\/\d{6}\/mod_folder\/content\/0\/(?:[\w\d\_\-]*\/)*[\w\d\_\-\.]{1,}'),
            response.text)
    #print("delta folder:", clock() - t)
    return hrefs


def get_file_links(session, url, files):
    links = []

    response = session.get(url)

    if 'www.moodle.tum.de' in url:
        # get file links
        hrefs = findall(compile('https\:\/\/www\.moodle\.tum\.de\/mod\/resource\/view\.php\?id\=\d{6}'), response.text)
        # resolve all links to direct to the files
        hrefs = resolve_direct_links(session, hrefs)
        # get folder links
        folders = findall(compile('https\:\/\/www\.moodle\.tum\.de\/mod\/folder\/view\.php\?id\=\d{6}'), response.text)
        if folders:
            hrefs += get_links_from_folder(session, folders)
    else:
        hrefs = html.fromstring(response.text).xpath('//a/@href')

    # ---------------
    t = clock()
    for f in files:
        reg = compile(f[0])
        for href in hrefs:
            match = reg.findall(href)
            if match:
                if not ('https://' in href or 'http://' in href):
                    links.append((url + href, f[1]))
                else:
                    links.append((href, f[1]))
    #print("delta regex:", clock() - t)
    return links


def establish_moodle_session(user, passwd):
    session = Session()

    session.get(
        'https://www.moodle.tum.de/Shibboleth.sso/Login?providerId=https://tumidp.lrz.de/idp/shibboleth&target=https://www.moodle.tum.de/auth/shibboleth/index.php')
    response = session.post('https://tumidp.lrz.de/idp/Authn/UserPassword',
                            data={'j_username': user, 'j_password': passwd})

    parsed = html.fromstring(response.text)

    session.post('https://www.moodle.tum.de/Shibboleth.sso/SAML2/POST',
                 data={'RelayState': parsed.forms[0].fields['RelayState'],
                       'SAMLResponse': parsed.forms[0].fields['SAMLResponse']})

    return session


def main(url, files, user='', passwd=''):
    # create session
    t = clock()
    if 'www.moodle.tum.de' in url:
        session = establish_moodle_session(user, passwd)
    else:
        session = Session()
        session.auth = (user, passwd)
        session.headers = {
            "Accept-Language": "de-DE,de;"
        }
    #print("delta session:", clock() - t)


    # get file links
    links = get_file_links(session, url, files)

    # download files
    #print(threading.active_count())
    t1 = clock()
    for l in links:
        while threading.active_count() > NUM_THREADS:
            sleep(0.02)
        Thread(target=download_files, args=(session, l)).start()

    while threading.active_count() > 1:
            #print(threading.active_count())
            sleep(0.5)
    #print("delta download threaded:", clock() - t1)
