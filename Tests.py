import unittest
from spider import Dates, Spider


class Testings(unittest.TestCase):
    def test_dates(self):
        dates = Dates()
        assert dates.begin.start == '01/01/1965'
        assert dates.begin.end == '01/02/1965'
        for date in dates:
            assert date.start == '01/03/1965'
            assert date.end == '01/04/1965'
            break

    def test_getting_cookies(self):
        dates = Dates()
        spider = Spider(dates)
        url = spider.make_POST(dates.begin)
        assert url

    def test_fetching_records_url(self):
        dates = Dates()
        spider = Spider(dates)
        result = spider.crawl_search_pages()
        items = [item for item in result]
        assert items

    def test_crawling_records(self):
        dates = Dates()
        spider = Spider(dates)
        unscraped = [
            {
                "grantor": " CASCADE PARK, R66 T5 S13 NW4 NE4 PT",
                "related": " ",
                "grantee": "ENV 303",
                "href": "../eagleweb/viewDoc.jsp?node=DOCC1453048",
                "rel_book_page": " ",
                "book_page": " ",
                "name": "VACATION AND DEDICATION PLAT",
                "id": "\n1453048"
            },
            {
                "grantor": " BOISE CASCADE CORP, CASCADE PARK",
                "related": " ",
                "grantee": "",
                "href": "../eagleweb/viewDoc.jsp?node=DOCCUSI1-1453048",
                "rel_book_page": " ",
                "book_page": " ",
                "name": "VACATION AND DEDICATION PLAT",
                "id": "\n1453048"
            },
            {
                "grantor": " PEPSI COLA BOTTLING CO DENVER",
                "related": " ",
                "grantee": "HILZRES PHILLIPS 66",
                "href": "../eagleweb/viewDoc.jsp?node=DOCCUSI1-1452928",
                "rel_book_page": " ",
                "book_page": " ",
                "name": "SECURITY AGREEMENT",
                "id": "\n1452928"
            },
            {
                "grantor": " CALIFORNIA PELLET MILL COMPANY",
                "related": " ",
                "grantee": "NORTHERN JEED GRAIN CO",
                "href": "../eagleweb/viewDoc.jsp?node=DOCCUSI1-1452988",
                "rel_book_page": " ",
                "book_page": " ",
                "name": "SECURITY AGREEMENT",
                "id": "\n1452988"
            },
            {
                "grantor": " ANDERSON SON",
                "related": " ",
                "grantee": "DUELL WAYNE",
                "href": "../eagleweb/viewDoc.jsp?node=DOCCUSI1-1452929",
                "rel_book_page": " ",
                "book_page": " ",
                "name": "CONTRACT OF SALE OF REAL ESTATE",
                "id": "\n1452929"
            }
        ]
        loop, future = spider.crawl_records(unscraped, None)
        loop.run_until_complete(future)


if __name__ == '__main__':
    unittest.main()
