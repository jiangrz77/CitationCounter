### Check requirments
import pkg_resources, pip
dependencies = ['beautifulsoup4>=4.11.2', 'selenium>=4.18.1']
try:
    pkg_resources.require(dependencies)
except pkg_resources.DistributionNotFound:
    pip.main(['install', '-r', 'requirements.txt'])


from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os, errno, re
import numpy as np
import pandas as pd
from pathlib import Path
from util import _abbr_chinese_name, _abbr_nonchinese_name


class CitationScraper:
    def __init__(self, file_path, out='output.csv', delete_self_cite=True, generate_bibtex=True, timeout=20):
        self.file_path = Path(file_path)
        self.del_self_cite = delete_self_cite
        self.bibtex = generate_bibtex
        self.time_out = timeout
        if not self.file_path.exists():
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(self.file_path.absolute()))
        self.read_article_title_from_file()
        self.adsquery_url = 'https://ui.adsabs.harvard.edu/search/q='
        self.adsabs_url = 'https://ui.adsabs.harvard.edu/abs/'
        self.get_all_citations()    # store in attr 'all_citations'
        if self.bibtex:
            self.build_bibtex()
        self.out_path = Path(out)
        print(self.all_citations.loc[0, 'article_authors'])
        self.all_citations.to_csv(self.out_path, encoding='utf-8', index=False)
        if self.del_self_cite:      # store in attr 'citation_del_selfcite'
            self.out_path_del_selcite = self.out_path.parent/(self.out_path.stem+'_delselfcite.csv')
            self.delete_self_cites()
            self.citation_del_selfcite.to_csv(self.out_path_del_selcite, encoding='utf-8', index=False)
        self.driver.close()
        # write to csv

    def read_article_title_from_file(self, ):
        with open(self.file_path, 'r', encoding='utf-8') as file:
            article_titles = [line.strip() for line in file.readlines()]
        self.article_titles = article_titles

    def get_all_citations(self, ):
        # declare a driver, need protability
        self.driver = webdriver.Chrome()
        column = ['article_title', 'article_authors', 'cite_index', 'cite_title', 'cite_authors', 'cite_bibcode']
        all_citations = pd.DataFrame(columns=column)
        self.nonrepeat_articles = []
        for article_title in self.article_titles:
            cite_dict = self.get_citations(article_title)
            if cite_dict=='Repeat':
                print('Repeated query detected. Skipping......')
                continue
            elif cite_dict is None:
                continue
            cite_length = len(cite_dict['cite_title'])
            if cite_length > 0:
                cite_dict['cite_index'] = range(1, cite_length+1)
                df_cite = pd.DataFrame(cite_dict, columns=column)
                all_citations = pd.concat((all_citations, df_cite), ignore_index=True)
                self.nonrepeat_articles.append(cite_dict['article_title'])
            else:
                print(f'No citation found for: {article_title}')
        self.all_citations = all_citations
    
    def delete_self_cites(self, ):
        all_citations = self.all_citations
        df_length = len(all_citations)
        flag_self_cite = np.full(df_length, True)
        for row_idx in range(df_length):
            row_article_authors = all_citations.loc[row_idx, 'article_authors'].split(';')
            row_cite_authors = all_citations.loc[row_idx, 'cite_authors'].split(';')
            flag_intersect = self._find_intersect_authors(
                row_article_authors, row_cite_authors, cross=False
            )
            if flag_intersect:
                flag_self_cite[row_idx] = False
            else:
                flag_intersect_cross = self._find_intersect_authors(
                    row_article_authors, row_cite_authors, cross=True
                )
                if flag_intersect_cross:
                    flag_self_cite[row_idx] = False
        df_citations_del_selfcite = all_citations.loc[flag_self_cite]
        self.citation_del_selfcite = df_citations_del_selfcite

    def build_bibtex(self, ):
        df_citations = self.all_citations
        for row_idx, row in df_citations.iterrows():
            bibcode = row['cite_bibcode']
            url = self.adsabs_url + bibcode + '/exportcitation'
            self.driver.get(url)
            # soup = self._driver_wait_element(By.ID, 'ex-dropdown')
            soup = self._driver_wait_element(By.CSS_SELECTOR, '.export-textarea.form-control')
            # export-textarea form-control
            if not soup:
                continue
            else:
                dict_bibtex = self._export_bibdict(soup)
                df_citations.loc[row_idx, dict_bibtex.keys()] = dict_bibtex.values()
        self.all_citations = df_citations

    def get_citations(self, article_title):
        print('Querying: %s'%article_title)
        query = article_title.replace(' ', '%20')
        query_url = self.adsquery_url + query
        self.driver.get(query_url)
        soup = self._driver_wait_element(By.CLASS_NAME, 'citations-redirect-link')
        if not soup:
            return
        cite_dict = {}
        cite_dict['article_title'] = soup.body.find('h3', {'class': 's-results-title'}).text.strip()
        # check redundant
        if cite_dict['article_title'] in self.nonrepeat_articles:
            return 'Repeat'
        article_authors_element = soup.body.find(
            'ul', {'class':"list-inline just-authors s-results-authors all-authors hidden"}
        ).find_all('li', {'class': 'article-author'})
        cite_dict['article_authors'] = ''.join(_.text for _ in article_authors_element)
        redirect_url = soup.find('a', {'class': 'citations-redirect-link'}, href=True)['href'].replace('#abs/', self.adsabs_url)
        self.driver.get(redirect_url)
        # self.driver.find_element(
        #     By.CLASS_NAME, 'citations-redirect-link'
        # ).click()

        soup = self._driver_wait_element(By.CSS_SELECTOR, '.page-control.next-page')
        if not soup:
            return
        page_control = soup.body.find_all(
            'input', {'class': 'form-control page-control'}
        )
        total_pages = int(page_control[0].parent.text.split('of')[-1].strip())
        for _page_num in range(total_pages):
            cite_dict_by_page = self._get_citations_by_page(soup)
            cite_dict.update(cite_dict_by_page)
            if _page_num < (total_pages - 1):
                self.driver.find_element(
                    By.CSS_SELECTOR, '.page-control.next-page'
                ).click()
        return cite_dict
    
    @staticmethod
    def _get_citations_by_page(soup):
        cite_dict_by_page = {}
        cite_dict_by_page['cite_title'] = soup.body.find_all('h3', {'class': 's-results-title'})
        cite_dict_by_page['cite_bibcode'] = soup.body.find_all('a', {'class': 'abs-redirect-link', 'aria-label': 'bibcode'})
        cite_dict_by_page['cite_authors'] = soup.body.find_all(
            'ul', {
                'class': 'list-inline just-authors s-results-authors '
                         'all-authors hidden'
            }
        )
        cite_len_by_page = len(cite_dict_by_page['cite_title'])
        for cite_num in range(cite_len_by_page):
            cite_dict_by_page['cite_title'][cite_num] = cite_dict_by_page['cite_title'][cite_num].text.strip()
            cite_dict_by_page['cite_bibcode'][cite_num] = cite_dict_by_page['cite_bibcode'][cite_num].text.strip()
            cite_dict_by_page['cite_authors'][cite_num] = ''.join(_.text for _ in cite_dict_by_page['cite_authors'][cite_num].find_all('li', {'class': 'article-author'}))
        return cite_dict_by_page

    @staticmethod
    def _export_bibdict(soup_exportcitation):
        bibtex = soup_exportcitation.body.find(
            'textarea', 
            {'class': 'export-textarea form-control'}
        ).text

        # Define the regex patterns
        doi_pattern = r'doi = {(.+?)}'
        journal_pattern = r'journal = {(.+?)}'
        year_pattern = r'year = (\d{4})'
        volume_pattern = r'volume = {(.+?)}'
        number_pattern = r'number = {(.+?)}'
        pages_pattern = r'pages = {(.+?)}'

        # Extract the fields
        doi = re.findall(doi_pattern, bibtex)
        journal = re.findall(journal_pattern, bibtex)
        year = re.findall(year_pattern, bibtex)
        volume = re.findall(volume_pattern, bibtex)
        number = re.findall(number_pattern, bibtex)
        pages = re.findall(pages_pattern, bibtex)

        # Create a dictionary to store the fields
        bibtex_fields = {
            'doi': doi[0] if doi else 'None',
            'journal': journal[0] if journal else 'None',
            'year': year[0] if year else 'None',
            'volume': volume[0] if volume else 'None',
            'number': number[0] if number else 'None',
            'pages': pages[0] if pages else 'None',
        }

        return bibtex_fields
    
    
    @staticmethod
    def _find_intersect_authors(article_authors, cite_authors, cross=False):
        article_last_name, article_first_name = np.array([_.split(', ') for _ in article_authors]).T
        if cross:
            cite_first_name, cite_last_name = np.array([_.split(', ') for _ in cite_authors]).T
        else:
            cite_last_name, cite_first_name = np.array([_.split(', ') for _ in cite_authors]).T
        # check last name repeated in cite articles
        flag_last_name_incite = np.in1d(article_last_name, cite_last_name)
        article_last_name_incite = article_last_name[flag_last_name_incite]
        if len(flag_last_name_incite) == 0:
            return False
        # check the first name of repeated last name is the same or not
        article_first_name_incite = article_first_name[flag_last_name_incite]
        for _last_name, _first_name in zip(
            article_last_name_incite, 
            article_first_name_incite
        ):
            repeated_first_name = cite_first_name[np.in1d(cite_last_name, _last_name)]
            # 1. first name totally consistent
            if _first_name in repeated_first_name:
                return True
            else:
                abbr_fmt = r'([A-Z]\.)'
                abbr_first_name = re.search(abbr_fmt,_first_name) # two-char 
                # 2.1 article author abbr
                if abbr_first_name:
                    cite_abbr_chn = [_abbr_chinese_name(_) for _ in repeated_first_name]
                    cite_abbr_nonchn = [_abbr_nonchinese_name(_) for _ in repeated_first_name]
                    if (_first_name in cite_abbr_chn) or (_first_name in cite_abbr_nonchn):
                        return True
                # 2.2 article not abbr
                else:
                    article_abbr_chn = _abbr_chinese_name(_first_name)
                    article_abbr_nonchn = _abbr_nonchinese_name(_first_name)
                    if (article_abbr_chn in repeated_first_name) or (article_abbr_nonchn in repeated_first_name):
                        return True
        return False

    def _driver_wait_element(self, type, id):
        try:
            WebDriverWait(
                self.driver, timeout=self.time_out
            ).until(EC.presence_of_element_located((type, id)))
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            return soup
        except TimeoutException:
            print('TimeoutException: Element %s not found'%id)
            return None
        
if __name__ == '__main__':
    # file_path = input('Please enter the path to the file with article titles:')
    file_path = 'example.txt'
    scraper = CitationScraper(file_path)

