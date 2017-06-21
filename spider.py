import os
import requests
import json
import re
import asyncio
import aiohttp
from multiprocessing.dummy import Pool as ThreadPool
from aiohttp import ClientSession
from time import sleep, time
from datetime import datetime,timedelta
from collections import namedtuple
from selenium import webdriver
from lxml import html
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from selenium.common.exceptions import TimeoutException, NoSuchElementException

number_of_scraped = 0
total_count = 0
main_page = 'https://searchicris.co.weld.co.us/recorder/web/login.jsp'
wd = webdriver.PhantomJS(os.path.join(os.path.dirname(__file__), 'bin/phantomjs'))
wd.set_page_load_timeout(60)

class Collector:
    def __init__(self):
        credentials = None
        mongodb_uri_exists = 'MONGODB_URI' in os.environ
        if mongodb_uri_exists:
            credentials = os.environ['MONGODB_URI']
        elif os.path.isfile('credentials.json'):
            credentials = open('credentials.json', 'r').read()
            credentials = json.loads(credentials)
            conn_string = 'mongodb://%s:%s@%s:%s/%s'
            credentials = conn_string % (credentials['user'],
                                         credentials['password'],
                                         credentials['host'],
                                         credentials['port'],
                                         credentials['db'])
        self.client = MongoClient(credentials)
        self.db = self.client['data']
        self.collection = self.db['records']

    def insert_one(self, d):
        try:
            self.collection.insert_one(d)
        except DuplicateKeyError:
            pass

    def get_unscraped_records_data(self, limit=0):
        return self.collection.find({"data" : {"$exists" : False}}).limit(limit)

    def get_records_without_pdf(self):
        return self.collection.find({"pdf_name" : {'$exists' : False}}, {'href' : 1, 'RECEPTION NO' : 1}).limit(500000)

    def get_records_without_pdf_using_instruments(self):
        return self.collection.find({"pdf_name" : {'$exists' : False}, 'INSTRUMENT TYPE' : 'OIL & GAS LEASE'}, {'href' : 1, 'RECEPTION NO' : 1})

    def set_pdf_url(self, _id, pdf_name):
        self.collection.update_one({'_id' : _id}, {'$set' : {'pdf_name' : pdf_name}})

    def update_one(self, doc, data):
        self.collection.update_one({'_id' : doc['_id']}, {'$set' : {'data' : data}})


class Dates:
    def __init__(self):
        self.format = '%m/%d/%Y'
        self._today = datetime.now()
        self.next = 0
        self._end = datetime.now() - timedelta(days=30)
        self._start = datetime.now() - timedelta(days=31)
        self.Date = namedtuple('Date', ['start', 'end'])
        self.begin = self.Date(self._start.strftime(self.format),
                          self._end.strftime(self.format))

    def __iter__(self):
        return self

    def __next__(self):
        if self.next == 0:
            self.next += 1
            return self.begin
        if self._end >= self._today:
            raise StopIteration
        else:
            self._start += timedelta(days=2)
            self._end += timedelta(days=2)
            date = self.Date(self._start.strftime(self.format)
                             , self._end.strftime(self.format))
            return date


class Spider():
    def __init__(self, dates):
        self.dates = dates
        self.refresh_cookie()
        self.mongodb = Collector()

    def refresh_cookie(self):
        wd.get(main_page)
        submit = wd.find_elements_by_name('submit')[0]
        submit.click()
        accept = wd.find_elements_by_name('accept')[0]
        accept.click()
        self.cookies = {cookie['name']: cookie['value']
                for cookie in wd.get_cookies()
                if '_ga' not in cookie['name']}

    def make_POST(self, date : namedtuple):
        '''Returns url of new data'''
        form_data_string = '''DocumentNumberID:
                            RecordingDateIDStart:
                            RecordingDateIDEnd:
                            BothNamesIDSearchString:
                            BothNamesIDSearchType:Basic Searching
                            BookPageIDBook:
                            BookPageIDPage:
                            GrantorIDSearchString:
                            GrantorIDSearchType:Basic Searching
                            GranteeIDSearchString:
                            GranteeIDSearchType:Basic Searching
                            PlattedLegalIDSubdivision:
                            PlattedLegalIDLot:
                            PlattedLegalIDBlock:
                            PlattedLegalIDTract:
                            PlattedLegalIDUnit:
                            PLSSLegalIDTract:
                            PLSSLegalIDSixtyFourthSection:
                            PLSSLegalIDSection:
                            PLSSLegalIDTownship:
                            PLSSLegalIDRange:
                            LegalRemarksID:
                            AllDocuments:ALL
                            docTypeTotal:1896'''
        form_data_string = form_data_string.split('\n')
        data = {part.split(':')[0].strip(): part.split(':')[1].strip()
                for part in form_data_string}
        data['RecordingDateIDStart'] = date.start
        data['RecordingDateIDEnd'] = date.end

        post_cookies = self.cookies
        post_cookies['sortDir'] = 'asc'
        post_cookies['pageSize'] = '100'
        response = requests.post('https://searchicris.co.weld.co.us/recorder/eagleweb/docSearchPOST.jsp',
                      data=data, cookies=self.cookies)
        if response.history:
            history = response.history[0]
            if 'location' in history.headers._store\
                    and len(history.headers._store['location']) == 2:
                return history.headers._store['location'][-1]
        return None

    def crawl_search_pages(self):
        def collect_links(url):
            '''Returns items + next page link'''
            response = requests.get(url, cookies=self.cookies)
            if 'You must be logged in to access the requested page' in response.text:
                self.refresh_cookie()
                return collect_links(url)
            if 'No results found' in response.text:
                return None, None
            document = html.fromstring(response.text)
            next_link = document.xpath("//span[@class='pagelinks']/strong/following-sibling::a")
            if next_link and 'next' not in next_link[0].xpath('.//text()'):
                next_link = next_link[0].xpath('./@href')[0]
            else:
                next_link = None
            items = []
            for tr in document.xpath("//table[@id='searchResultsTable']/tbody/tr"):
                d = {}
                td1 = tr.xpath("./td[position()=1]")[0]
                d['href'] = td1.xpath(".//a/@href")[0]
                d['header'] = html.tostring(tr).decode()
                items.append(d)
            return items, next_link
        url_first_part = 'https://searchicris.co.weld.co.us/recorder'
        for date in self.dates:
            #Scraping the first page
            print('Scraping date: ' + str(date))
            items = []
            created_url = self.make_POST(date)
            url = url_first_part + created_url[2:]
            collected_links, next_page = collect_links(url)
            if collected_links: items += collected_links
            while next_page:
                collected_links, next_page = collect_links(url_first_part.replace('recorder','') + next_page)
                if collected_links: items += collected_links
            print("Scraped " + str(len(items)) + " from " + date.start + " - " + date.end)
            if items:
                for item in items:
                    self.mongodb.insert_one(item)

    def crawl_records(self):
        def go(record):
            print('Scraping record')
            global number_of_scraped
            global total_count
            if 'You must be logged in to access the requested page' in wd.page_source:
                print('Refreshing cookies')
                self.refresh_cookie()
            if 'Maximum Page Requests Exceeded' in wd.page_source:
                print('Maximum page requests')
                sleep(3)
                go(record)
                return
            sleep(1)
            div = wd.find_element_by_id('presentation').get_attribute('innerHTML')
            data = {}
            if div:
                data['data'] = re.sub('(<!--.*?-->)', '', div).replace('\n', '').replace('\t', '')
            else:
                print('Lose id in ' + record['href'])

            if data:
                total_count += 1
                print('Scraped ' + record['id'].strip() + ' Total: ' + str(total_count) + ' Time: ' + str(datetime.now()))
                self.mongodb.update_one(record, data)

        for record in self.mongodb.get_unscraped_records_data():
            for i in range(0,3):
                try:
                    go(record)
                    break
                except NoSuchElementException:
                    pass
                except TimeoutException:
                    pass

    def upload_pdfs(self):
        main_page_url = 'https://searchicris.co.weld.co.us/recorder/web/login.jsp'
        credentials = json.load(open('credentials.json', 'r'))
        self.amazon_url = credentials['amazon_url']
        wd.get(main_page_url)
        wd.find_element_by_id('userId').send_keys(credentials['icris_user'])  # login
        wd.find_element_by_name('password').send_keys(credentials['icris_password'])  # password
        wd.find_elements_by_name('submit')[1].click()
        cookies = {cookie['name']: cookie['value']
                   for cookie in wd.get_cookies()
                   if '_ga' not in cookie['name']}
        cookies = {'JSESSIONID': cookies['JSESSIONID'], 'f5_cspm': cookies['f5_cspm'],
                   'pageSize': '100', 'sortDir': 'asc', 'sortField': 'Document+Relevance'}

        def fetch(record):
            global total_count
            if 'RECEPTION NO' not in record: return
            if 'href' not in record: return
            _id = record['_id']
            reception = record['RECEPTION NO']
            second_part = record['href'].split('=')[-1]
            url = 'https://searchicris.co.weld.co.us/recorder/eagleweb/downloads/' + reception + '?id=' + second_part + '.A0&parent=' + second_part + '&preview=false&noredirect=true'
            for i in range(0, 3):
                try:
                    response = requests.get(url, cookies=cookies, timeout=60)
                    if response.status_code == 200:
                        pdf_name = '%s-%s.pdf' % (reception, second_part)
                        amazon_response = requests.post(self.amazon_url, data={'filename': pdf_name},
                                                files={'file': response.content})
                        if amazon_response.status_code == 200:
                            self.mongodb.set_pdf_url(_id, pdf_name)
                            total_count += 1
                            print('Fetched pdfs: ' + str(total_count))
                    break
                except requests.exceptions.Timeout:
                    continue
                except requests.exceptions.ConnectionError:
                    continue

        pool = ThreadPool(5)
        pool.map(fetch, self.mongodb.get_records_without_pdf())
        pool.close()
        pool.join()

if __name__ == '__main__':
    dates = Dates()
    spider = Spider(dates)
    spider.crawl_search_pages()
    spider.crawl_records()
    total_count = 0
    spider.upload_pdfs()
    print('Finished')

