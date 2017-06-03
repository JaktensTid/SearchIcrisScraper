import os
import sys
import requests
import json
import re
import gc
from datetime import datetime
from lxml.html import tostring
from time import sleep, time
from datetime import datetime,timedelta
from collections import namedtuple
from selenium import webdriver
from lxml import html
from pymongo import MongoClient
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
        self.db = self.client['main']
        self.collection = self.db['records']

    def insert_one(self, d):
        self.collection.insert_one(d)

    def insert_many(self, items):
        self.collection.insert_many(items)

    def get_unscraped_records_data(self, skip):
        return self.collection.find({"data" : {"$exists" : False}}).limit(skip)

    def get_unscraped_records_headers(self, skip):
        return self.collection.find({"header": {"$exists": False}}).limit(skip)

    def update_one(self, doc, data):
        self.collection.update_one({'_id' : doc['_id']}, {'$set' : {'data' : data}})

    def update_by_href(self, href, header):
        self.collection.update_one({'href': href}, {'$set': {'header': header}})


class Dates:
    def __init__(self, start=None, end=None):
        self.format = '%m/%d/%Y'
        self._today = datetime.now()
        self.next = 0
        if start:
            self._start = datetime.strptime(start, self.format)
        else:
            self._start = datetime.strptime('03/30/1994', self.format)
        if end:
            self._end = datetime.strptime(end, self.format)
        else:
            self._end = datetime.strptime('03/31/1994', self.format)
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
            '''Returns links + next page link'''
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
            links = []
            created_url = self.make_POST(date)
            url = url_first_part + created_url[2:]
            collected_links, next_page = collect_links(url)
            if collected_links: links += collected_links
            while next_page:
                collected_links, next_page = collect_links(url_first_part.replace('recorder','') + next_page)
                if collected_links: links += collected_links
            print("Scraped " + str(len(links)) + " from " + date.start + " - " + date.end)
            yield links

    def run(self, unscraped, collector):
        base_url = 'https://searchicris.co.weld.co.us/recorder'
        def go(record):
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
                collector.update_one(record, data)

        for record in unscraped:
            for i in range(0,3):
                try:
                    go(record)
                    break
                except NoSuchElementException:
                    pass
                except TimeoutException:
                    pass 


if __name__ == '__main__':
    dates = None
    app_code = 1
    if len(sys.argv) == 3:
        dates = Dates(sys.argv[1], sys.argv[2])
    if len(sys.argv) == 2:
        app_code = int(sys.argv[1])
    else:
        dates = Dates()
    spider = Spider(dates)
    collector = Collector()
    for links in spider.crawl_search_pages():
        for link in links:
            collector.update_by_href(**link)
    print('Finished')

