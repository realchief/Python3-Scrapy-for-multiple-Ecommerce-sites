# - * - coding: utf-8 -*-#
from __future__ import absolute_import, division, unicode_literals

from scrapy import Request, FormRequest
from scrapy.log import WARNING
import re
import time
import json
import math
import requests
from scrapy.conf import settings

from HP_Master_Project.utils import clean_list
from HP_Master_Project.items import ProductItem
from HP_Master_Project.spiders import BaseProductsSpider
from HP_Master_Project.extract_brand import extract_brand_from_first_words


class ZonesSpider(BaseProductsSpider):
    name = 'zones_products'
    allowed_domains = ['zones.com', "www.zones.com"]

    SEARCH_URL = "http://www.zones.com/site/locate/search.html?txt_search={search_term}"

    API_URL = 'https://admin.metalocator.com/webapi/api/matchedretailerproducturls?Itemid=8343' \
              '&apikey=f5e4337a05acceae50dc116d719a2875&username=fatica%2Bscrapingapi@gmail.com' \
              '&password=8y3$u2ehu2e..!!$$&retailer_id={retailer_id}'

    PAGINATE_URL = "http://www.zones.com/site/locate/refine.html?&preserve=true"

    STOCK_STATUS_URL = "http://www.zones.com/site/productinventory/realtimeInventory.xml" \
                       "?productId={prod_id}&_={time}"

    HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/60.0.3112.90 Safari/537.36"}

    def __init__(self, *args, **kwargs):
        self.is_category = False
        super(ZonesSpider, self).__init__(
            site_name=self.allowed_domains[0], *args, **kwargs)
        self.user_agent = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/60.0.3112.90 Safari/537.36")
        settings.overrides['DOWNLOADER_CLIENTCONTEXTFACTORY'] = 'HP_Master_Project.utils.TLSFlexibleContextFactory'
        self.retailer_check = False

    def start_requests(self):
        for request in super(ZonesSpider, self).start_requests():
            if not self.product_url:
                request = request.replace(callback=self.parse_search, headers=self.HEADERS)
            yield request

    def parse_search(self, response):
        page_title = response.xpath('//div[@class="page-title"]').extract()
        if page_title or self.retailer_id:
            return self.parse(response)

        else:
            category_url = response.xpath('//div[@class="solutions-learn-more"]/a/@href').extract()
            for c_url in category_url:
                return Request(url=c_url, meta=response.meta, callback=self.parse_category_link)

    @staticmethod
    def parse_category_link(response):
        link = response.xpath('//a[@class="learn-more-link"]/@href').extract()
        if link:
            yield Request(url=link[0], meta=response.meta, dont_filter=True)

    def _parse_single_product(self, response):
        return self.parse_product(response)

    def parse_product(self, response):
        product = response.meta['product']

        # Parse name
        name = self._parse_name(response)
        product['name'] = name

        # Parse image
        image = self._parse_image(response)
        product['image'] = image

        # Parse model
        model = self._parse_model(response)
        product['model'] = model

        # Parse ean
        product['ean'] = None

        # Parse currencycode
        product['currencycode'] = 'USD'

        # Set locale
        product['locale'] = 'en-US'

        # Parse sku
        sku = self._parse_sku(response)
        product['sku'] = sku

        # Parse manufacturer
        manufacturer = self._parse_manufacturer(response)
        product['manufacturer'] = manufacturer

        # Parse categories
        categories = self._parse_categories(response)
        product['categories'] = categories

        # Parse price
        price = self._parse_price(response)
        product['price'] = price

        # Parse sale price
        product['saleprice'] = price

        # Parse retailer_key
        retailer_key = self._parse_retailer_key(response)
        product['retailer_key'] = retailer_key

        # Parse in_store
        in_store = self._parse_instore(response)
        product['instore'] = in_store

        # Parse gallery
        product['gallery'] = self._parse_gallery(response)

        # Parse features
        features = self._parse_features(response)
        product['features'] = features

        # Parse condition
        product['condition'] = 1

        product_id = response.xpath('//input[@id="product_id"]/@value').extract()
        if product_id:
            current_time = int(round(time.time() * 1000))
            return Request(
                url=self.STOCK_STATUS_URL.format(prod_id=product_id[0],
                                                 time=current_time),
                callback=self._parse_stock_status,
                dont_filter=True,
                meta={"product": product},
                headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
                                       'Chrome/60.0.3112.90 Safari/537.36'}
            )

        return product

    @staticmethod
    def _parse_name(response):
        title = response.xpath('//span[contains(@id, "product_name_id")]//text()').extract()
        if title:
            return title[0]

    @staticmethod
    def _parse_image(response):
        img = response.xpath('//div[@class="product-image"]//img[contains(@class, "primary-image")]'
                             '/@src').extract()
        if img:
            return img[0]

    def _parse_sku(self, response):
        sku = response.xpath('//span[@id="item_no_id"]/text()').extract()
        if sku:
            return self.clear_text(sku[0])

    def _parse_stock_status(self, response):
        product = response.meta['product']
        stock_value = 4

        try:
            stock_message = re.search("<stockMessage>(.*)</stockMessage>", response.body)
            if stock_message:
                stock_message = stock_message.group(1)

                if stock_message.lower() == 'in stock':
                    stock_value = 1
                elif stock_message.lower() == 'out of stock':
                    stock_value = 0
                elif stock_message.lower() == 'call for availability':
                    stock_value = 2
                elif stock_message.lower() == 'discontinued':
                    stock_value = 3
                else:
                    stock_value = 4
            else:
                stock_value = 4

            product['productstockstatus'] = stock_value
            return product

        except BaseException as e:
            self.log("Error parsing stock status data: {}".format(e), WARNING)
            product['productstockstatus'] = stock_value
            return product

    @staticmethod
    def _parse_categories(response):
        categories = response.xpath('//li[contains(@typeof, "Breadcrumb")]/a/text()').extract()
        return categories

    def _parse_model(self, response):
        model = response.xpath('//span[contains(@id, "mfr_no_id")]/text()').extract()
        if model:
            return self.clear_text(model[0])

    @staticmethod
    def _parse_gallery(response):
        gallery = response.xpath('//div[@class="thumbs-wrapper"]/ul[@ng-hide="showThumbnails"]/li/img/@src').extract()
        return gallery

    @staticmethod
    def _parse_price(response):
        price = response.xpath('//span[@class="prod-price"]/text()').extract()
        if price:
            return float(price[0].replace("$", "").replace(",", ""))

    def _parse_retailer_key(self, response):
        retailer_key = response.xpath('//span[@id="item_no_id"]/text()').extract()
        if retailer_key:
            return self.clear_text(retailer_key[0])

    def _parse_instore(self, response):
        if self._parse_price(response):
            return 1

        return 0

    def _parse_manufacturer(self, response):
        manufacture = re.search('name="mfgrname" value="(.*?)"', response.body)
        if manufacture:
            return self.clear_text(manufacture.group(1))

    def _parse_features(self, response):
        features = []
        features_name = response.xpath('//span[@class="ppdefaultbold"]/text()').extract()
        features_value = response.xpath('//div[@class="sumCont"]//li/text()').extract()
        features_value = clean_list(self, features_value)

        for f_name in features_name:
            index = features_name.index(f_name)
            feature = {f_name: features_value[index]}
            features.append(feature)

        return features

    def clear_text(self, str_result):
        return str_result.replace("\t", "").replace("\n", "").replace("\r", "").replace(u'\xa0', ' ').strip()

    def _scrape_total_matches(self, response):
        if self.retailer_id:
            data = json.loads(response.body)
            return len(data)
        totals = response.xpath('//div[@class="serp-item-count"]').extract()
        if totals:
            totals = totals[0]
            totals = re.search("of <strong>(.*)</strong>", totals)
            if totals:
                totals = totals.group(1).replace(',', '').replace('.', '').strip()
                if totals.isdigit():
                    return int(totals)

    def _scrape_product_links(self, response):
        link_data = []
        if self.retailer_id:
            data = requests.get(self.API_URL.format(retailer_id=self.retailer_id)).json()
            link_list = data
            for link in link_list:
                link = link['product_link']
                link_data.append(link)
            for link in link_data:
                yield link, ProductItem()
        else:
            links = response.xpath('//div[contains(@class, "serp-results")]/div[@class="product"]'
                                   '/a[@class="title"]/@href').extract()
            for link in links:
                yield link, ProductItem()

    def _scrape_next_results_page_link(self, response):
        if self.retailer_id:
            return None

        meta = response.meta

        total_matches = self._scrape_total_matches(response)
        results_per_page = self._scrape_results_per_page(response)

        current_page = meta.get('current_page')
        if not current_page:
            current_page = 1

        if (total_matches and results_per_page and
                    current_page < math.ceil(total_matches / float(results_per_page))):
            current_page += 1
            meta['current_page'] = current_page

            return FormRequest(
                url=self.PAGINATE_URL,
                formdata={
                  "searchType": "browse_search",
                  "submit_name": "select_compare_form",
                  "page_number": str(current_page),
                  "partner_id": "",
                  "compareChecks": "",
                  "compare_maxed": ""
                },
                dont_filter=True,
                headers=self.HEADERS,
                meta=meta
            )
