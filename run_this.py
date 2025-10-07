from CitationScraper import CitationScraper as CS

CS(
    'example.txt', out='output.csv', 
    delete_self_cite=True, #generate_bibtex=True
)
# CS('example.txt', out='output.csv')