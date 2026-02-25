import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import fitz  # PyMuPDF
import re
import streamlit as st
import os
import subprocess
import sys
from pathlib import Path

# Ensure packages are installed
required = {
    'beautifulsoup4==4.12.3',
    'soupsieve==2.5'
}
installed = {pkg.key for pkg in __import__('pkg_resources').working_set}
missing = required - installed

if missing:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', *missing], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL)

if 'reset_counter' not in st.session_state:
    st.session_state.reset_counter = 0
if 'show_success' not in st.session_state:
    st.session_state.show_success = False
if 'xml_data' not in st.session_state:
    st.session_state.xml_data = None
if 'filename' not in st.session_state:
    st.session_state.filename = "formatted_article_set.xml"
if 'processed_xml' not in st.session_state:
    st.session_state.processed_xml = None
if 'show_combine_section' not in st.session_state:
    st.session_state.show_combine_section = False
if 'final_combined_xml' not in st.session_state:
    st.session_state.final_combined_xml = None

def parse_date(date_str):
    for fmt in ["%d %B %Y", "%B %d, %Y", "%d %b %Y", "%b %d, %Y"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            return str(dt.year), f"{dt.month:02d}", f"{dt.day:02d}"
        except:
            continue
    return "null", "null", "null"

def extract_history_from_pdf(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        combined_date = r"(?:[A-Za-z]{3,9}\s+\d{1,2},?\s*\d{4}|\d{1,2}\s+[A-Za-z]{3,9},?\s*\d{4})"

        patterns = [
            re.compile(rf"(?i)Received\s*[:\-]?\s*({combined_date}),\s*Accepted\s*[:\-]?\s*({combined_date})"),
            re.compile(rf"(?i)Received\s+({combined_date})\s+Accepted\s+({combined_date})"),
            re.compile(rf"(?i)Received\s+on\s+({combined_date})\s*;\s*Accepted\s+on\s+({combined_date})"),
            re.compile(rf"(?i)Received[:\-]?\s*({combined_date})\s*\|\s*(?:Revised[:\-]?\s*{combined_date}\s*\|\s*)?Accepted[:\-]?\s*({combined_date})"),
            re.compile(rf"(?i)Received\s*[:\-]?\s*({combined_date})\s*;\s*Accepted\s*[:\-]?\s*({combined_date})"),
        ]

        for page in doc:
            text = page.get_text()
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    r, a = match.group(1).strip(), match.group(2).strip()
                    return parse_date(r), parse_date(a)
        return None  # Return None when dates aren't found
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
        return None

def clear_form():
    st.session_state.reset_counter += 1
    st.session_state.show_success = True
    st.session_state.xml_data = None
    st.session_state.processed_xml = None
    st.session_state.filename = "formatted_article_set.xml"
    st.session_state.show_combine_section = False
    st.session_state.final_combined_xml = None

def extract_journal_abbreviation(doi):
    """Extract journal abbreviation from DOI"""
    if not doi:
        return "null"
    
    # Split DOI by both '/' and '.'
    parts = re.split(r'[/.]', doi)
    
    # Find the abbreviation part (usually the part before the year)
    for i, part in enumerate(parts):
        if part.isdigit() and len(part) == 4:  # Year found
            if i > 0:
                return parts[i-1].upper()  # Return the part before the year
    return "null"

def generate_filename(article_url, xml_content):
    try:
        root = ET.fromstring(xml_content)
        
        # Extract DOI components
        doi_elem = root.find(".//ELocationID[@EIdType='doi']")
        last_doi_digit = ""
        if doi_elem is not None and doi_elem.text:
            doi = doi_elem.text.strip()
            parts = doi.split(".")
            last_part = parts[-1]
            last_doi_digit = last_part if last_part.isdigit() else ""

        # Extract number from URL
        numbers = re.findall(r'\d+', article_url)
        last_url_num = numbers[-1] if numbers else "-"
        
        # Initialize volume and issue
        volume = root.findtext(".//Volume", "").strip()
        issue = root.findtext(".//Issue", "").strip()

        # If not found in standard tags, try to extract from DOI
        if not volume or not issue:
            if doi_elem is not None and doi_elem.text:
                doi = doi_elem.text.strip()
                parts = doi.split('.')
                
                # Find the position of the 4-digit year
                year_pos = -1
                for i, part in enumerate(parts):
                    if len(part) == 4 and part.isdigit():
                        year_pos = i
                        break
                
                # Extract volume and issue if pattern matches
                if year_pos != -1 and len(parts) > year_pos + 2:
                    volume = parts[year_pos + 1] if not volume else volume
                    issue = parts[year_pos + 2] if not issue else issue

        # Set defaults if still not found
        vol_num = volume if volume else "-"
        issue_num = issue if issue else "-"
        
        # Extract year
        year = "null"
        try:
            response = requests.get(article_url)
            soup = BeautifulSoup(response.content, "html.parser")
            published_div = soup.find("div", class_="list-group-item date-published")
            if published_div:
                text = published_div.get_text(strip=True).replace("Published:", "").strip()
                year, _, _ = parse_date(text)
        except Exception as e:
            st.warning(f"Could not extract year from article URL: {str(e)}")
            pub_date = root.find(".//PubDate[@PubStatus='pub']")
            if pub_date is not None:
                year_elem = pub_date.find("Year")
                if year_elem is not None and year_elem.text:
                    year = year_elem.text.strip()
        
        # Construct filename parts
        parts = [
            last_doi_digit,
            last_url_num,
            f"Vol.{vol_num}",
            f"No.{issue_num}",
            year
        ]
        return "_".join(filter(None, parts)) + ".xml"  # filter removes empty parts
    except Exception as e:
        st.warning(f"Could not generate filename: {str(e)}")
        return "formatted_article_set.xml"
    
def indent(elem, level=0):
    indent_str = "  "
    newline = "\n"
    
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = newline + indent_str * (level + 1)
        
        for i, child in enumerate(elem):
            indent(child, level + 1)
            
            if i < len(elem) - 1:
                if not child.tail or not child.tail.strip():
                    child.tail = newline + indent_str * (level + 1)
            else:
                if not child.tail or not child.tail.strip():
                    child.tail = newline + indent_str * level
    
    else:
        if level > 0 and (not elem.tail or not elem.tail.strip()):
            elem.tail = newline + indent_str * level

def process_files(pdf_file, input_xml, article_url, pdf_link):
    try:
        temp_pdf = "temp_uploaded.pdf"
        temp_xml = "temp_uploaded.xml"
        
        with st.spinner("Processing files..."):
            # Save uploaded files temporarily
            with open(temp_pdf, "wb") as f:
                f.write(pdf_file.getbuffer())
            with open(temp_xml, "wb") as f:
                f.write(input_xml.getbuffer())

            # Read XML content
            with open(temp_xml, "r", encoding="utf-8") as f:
                xml_content = f.read()
            
            st.session_state.filename = generate_filename(article_url, xml_content)
            
            tree = ET.parse(temp_xml)
            root = tree.getroot()
            article = root.find(".//Article")
            
            if article is None:
                raise ValueError("No Article element found in the input XML")

            # Journal metadata processing
            journal = article.find("Journal")
            jt_elem = journal.find("JournalTitle") if journal is not None else None
            issn_elem = journal.find("Issn") if journal is not None else None
            doi_elem = article.find(".//ELocationID[@EIdType='doi']")
            
            if jt_elem is None or issn_elem is None:
                raise ValueError("Journal title or ISSN not found")

            journal_title = jt_elem.text.strip()
            shortcode = extract_journal_abbreviation(doi_elem.text if doi_elem is not None else "")
            pmc_id = shortcode.lower()
            
            # Create XML structure
            article_out = ET.Element("Article")
            journal_meta = ET.SubElement(article_out, "Journal-meta")
            
            # Add journal identifiers
            for id_type, val in [("pmc", pmc_id), ("pubmed", journal_title), ("publisher", shortcode)]:
                ET.SubElement(journal_meta, "journal-id", {"journal-id-type": id_type}).text = val
            
            ET.SubElement(journal_meta, "Issn").text = issn_elem.text.strip()
            publisher = ET.SubElement(journal_meta, "Publisher")
            ET.SubElement(publisher, "PublisherName").text = "MMU Press, Multimedia University"
            ET.SubElement(journal_meta, "JournalTitle").text = journal_title

            # Article metadata
            article_meta = ET.SubElement(article_out, "article-meta")

            # DOI and custom ID
            doi_elem = article.find(".//ELocationID[@EIdType='doi']")
            ET.SubElement(article_meta, "article-id", {"pub-id-type": "doi"}).text = doi_elem.text.strip() if doi_elem is not None else "null"
            
            volume = article.findtext(".//Volume", "").strip()
            issue = article.findtext(".//Issue", "").strip()

            # If not found, try to extract from DOI
            if not volume or not issue:
                doi_elem = article.find(".//ELocationID[@EIdType='doi']")
                if doi_elem is not None and doi_elem.text:
                    doi = doi_elem.text.strip()
                    # Extract the parts after the year (assuming format like 10.xxx/xxx.YYYY.V.I...)
                    parts = doi.split('.')
                    
                    # Find the position of the 4-digit year
                    year_pos = -1
                    for i, part in enumerate(parts):
                        if len(part) == 4 and part.isdigit():
                            year_pos = i
                            break
                    
                    # If year found and there are at least 2 parts after it
                    if year_pos != -1 and len(parts) > year_pos + 2:
                        volume = parts[year_pos + 1]  # Part after year is volume
                        issue = parts[year_pos + 2]  # Next part is issue

            # For handle page number
            try:
                fp_text = article.findtext(".//FirstPage", "0").strip()
                lp_text = article.findtext(".//LastPage", "0").strip()

                # Initialize default values
                fp = 0
                lp = 0

                # Extract first page number (split on en dash '–' or hyphen '-')
                if fp_text and '–' in fp_text:
                    fp = int(fp_text.split('–')[0])
                elif fp_text and '-' in fp_text:
                    fp = int(fp_text.split('-')[0])
                else:
                    fp = int(fp_text) if fp_text.isdigit() else 0

                # Extract last page number (split on en dash '–' or hyphen '-')
                if lp_text and '–' in lp_text:
                    lp = int(lp_text.split('–')[1])
                elif lp_text and '-' in lp_text:
                    lp = int(lp_text.split('-')[1])
                else:
                    lp = int(lp_text) if lp_text.isdigit() else 0

                # Calculate page count (ensure lp >= fp to avoid negative values)
                page_count = str(max(0, lp - fp + 1)) if lp >= fp else "0"
            except:
                page_count = "null"

            custom_id = f"{shortcode[0].lower()}{shortcode}.v{volume}.i{issue}.pg{str(fp)}"
            ET.SubElement(article_meta, "article-id", {"pub-id-type": "other"}).text = custom_id

            # Title
            title_elem = article.find("ArticleTitle")
            ET.SubElement(article_meta, "ArticleTitle").text = title_elem.text.strip() if title_elem is not None else "null"

            # Authors
            author_list = article.find("AuthorList")
            if author_list is not None:
                article_meta.append(author_list)
            else:
                ET.SubElement(article_meta, "AuthorList")

            # Publication dates from webpage
            try:
                response = requests.get(article_url)
                soup = BeautifulSoup(response.content, "html.parser")
                year, month, day = "null", "null", "null"
                
                published_div = soup.find("div", class_="list-group-item date-published")
                if published_div:
                    text = published_div.get_text(strip=True).replace("Published:", "").strip()
                    year, month, day = parse_date(text)

                # Add publication dates
                epublish_date = article.find(".//PubDate[@PubStatus='epublish']")
                if epublish_date is not None:
                    article_meta.append(epublish_date)

                for pub_type in ['pub', 'cover']:
                    pd_elem = ET.Element("PubDate", {"PubStatus": pub_type})
                    for tag, val in zip(["Year", "Month", "Day"], [year, month, day]):
                        ET.SubElement(pd_elem, tag).text = val
                    article_meta.append(pd_elem)

                # Keywords
                keywords_elem = ET.SubElement(article_meta, "Keywords")
                for meta in soup.find_all("meta", {"name": "citation_keywords"}):
                    keywords_content = meta.get("content", "")
                    for kw in re.split(r'[;,]\s*', keywords_content):
                        kw = kw.strip()
                        if kw:
                            kw_elem = ET.SubElement(keywords_elem, "Keyword")
                            ET.SubElement(kw_elem, "italic").text = kw
            except Exception as e:
                st.warning(f"Could not scrape article URL: {str(e)}")

            # Volume/Issue/Pages
            ET.SubElement(article_meta, "Volume").text = volume
            ET.SubElement(article_meta, "Issue").text = issue

            # Create tagging for first page, last page and page count
            ET.SubElement(article_meta, "FirstPage").text = str(fp)
            ET.SubElement(article_meta, "LastPage").text = str(lp)
            ET.SubElement(article_meta, "PageCount").text = page_count

            # Date extraction with strict validation
            dates = extract_history_from_pdf(temp_pdf)
            
            # If dates not found in PDF or invalid, show dropdown selectors
            if dates is None or dates == (("null", "null", "null"), ("null", "null", "null")):
                st.warning("Could not automatically extract valid dates from PDF. Please select them below:")
                
                # Date input section with dropdowns
                with st.container():
                    st.markdown("### Required Date Information")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Received date dropdowns
                        st.markdown("**Received Date**")
                        r_col1, r_col2, r_col3 = st.columns(3)
                        r_day = r_col1.selectbox("Day", [""] + list(range(1, 32)), index=0, key="received_day")
                        r_month = r_col2.selectbox("Month", [""] + [
                            "January", "February", "March", "April", "May", "June",
                            "July", "August", "September", "October", "November", "December"
                        ], index=0, key="received_month")
                        # Static year range that automatically includes current year
                        r_year = r_col3.selectbox("Year", [""] + list(range(1980, datetime.now().year + 1)), 
                                         index=0, key="received_year")
                    
                    with col2:
                        # Accepted date dropdowns
                        st.markdown("**Accepted Date**")
                        a_col1, a_col2, a_col3 = st.columns(3)
                        a_day = a_col1.selectbox("Day", [""] + list(range(1, 32)), index=0, key="accepted_day")
                        a_month = a_col2.selectbox("Month", [""] + [
                            "January", "February", "March", "April", "May", "June",
                            "July", "August", "September", "October", "November", "December"
                        ], index=0, key="accepted_month")
                        a_year = a_col3.selectbox("Year", [""] + list(range(1980, datetime.now().year + 1)),
                                         index=0, key="accepted_year")
                    
                    # Only proceed if all date fields are selected
                    if not all([r_day, r_month, r_year, a_day, a_month, a_year]):
                        return None
                    
                    # Format the selected dates
                    received_date_str = f"{r_day} {r_month} {r_year}"
                    accepted_date_str = f"{a_day} {a_month} {a_year}"
                    
                    dates = (
                        parse_date(received_date_str),
                        parse_date(accepted_date_str)
                    )
            else:
                st.success("✓ Automatically extracted valid dates from PDF")

            # Add dates to XML
            (r_year, r_month, r_day), (a_year, a_month, a_day) = dates
            history_elem = ET.Element("History")
            for status, y, m, d in [("received", r_year, r_month, r_day), ("accepted", a_year, a_month, a_day)]:
                pubdate = ET.SubElement(history_elem, "PubDate", {"PubStatus": status})
                ET.SubElement(pubdate, "Year").text = y
                ET.SubElement(pubdate, "Month").text = m
                ET.SubElement(pubdate, "Day").text = d
            article_meta.append(history_elem)

            # Abstract
            abstract = article.find("Abstract")
            abs_elem = ET.SubElement(article_meta, "abstract")
            p_elem = ET.SubElement(abs_elem, "p")
            p_elem.text = abstract.text.strip() if abstract is not None else "null"

            # Links and language
            ET.SubElement(article_meta, "pdf-link").text = pdf_link if pdf_link else "null"
            ET.SubElement(article_meta, "full_text_url").text = article_url if article_url else "null"
            ET.SubElement(article_meta, "Language").text = "eng"

            # Format and store XML
            indent(article_out)
            xml_str = ET.tostring(article_out, encoding='utf-8', method='xml').decode()
            
            st.session_state.processed_xml = xml_str
            st.session_state.show_combine_section = True
            
            # Only show success messages after processing completes
            st.success("✓ Dates selected successfully")
            st.success("Initial XML processing complete! You can now combine with template XML.")
            
            with st.expander("Preview Processed XML Output"):
                st.code(xml_str[:2000] + "..." if len(xml_str) > 2000 else xml_str, language="xml")

    except Exception as e:
        st.error(f"An error occurred during processing: {str(e)}")
    finally:
        # Clean up temporary files
        if os.path.exists(temp_pdf):
            os.remove(temp_pdf)
        if os.path.exists(temp_xml):
            os.remove(temp_xml)

def combine_with_template(template_file):
    try:
        temp_template = "temp_template.xml"
        
        with st.spinner("Combining with template..."):
            with open(temp_template, "wb") as f:
                f.write(template_file.getbuffer())
            
            processed_root = ET.fromstring(st.session_state.processed_xml)
            front = ET.Element("front")
            front.text = "\n  "
            article = ET.SubElement(front, "Article")
            article.text = "\n    "
            
            def copy_element(source, target, indent_level):
                indent = "  " * indent_level
                for elem in source:
                    new_elem = ET.SubElement(target, elem.tag)
                    if elem.text:
                        new_elem.text = elem.text
                    if elem.attrib:
                        new_elem.attrib.update(elem.attrib)
                    new_elem.tail = f"\n{indent}"
                    if len(elem) > 0:
                        new_elem.text = f"\n{indent}  "
                        copy_element(elem, new_elem, indent_level + 1)
                        new_elem[-1].tail = f"\n{indent}"
            
            journal_meta = processed_root.find("Journal-meta")
            if journal_meta is not None:
                new_journal_meta = ET.SubElement(article, "Journal-meta")
                new_journal_meta.text = "\n      "
                copy_element(journal_meta, new_journal_meta, 3)
                new_journal_meta[-1].tail = "\n    "
                new_journal_meta.tail = "\n    "
            
            article_meta = processed_root.find("article-meta")
            if article_meta is not None:
                new_article_meta = ET.SubElement(article, "article-meta")
                new_article_meta.text = "\n      "
                copy_element(article_meta, new_article_meta, 3)
                new_article_meta[-1].tail = "\n    "
                new_article_meta.tail = "\n  "
            
            article.tail = "\n"
            xml_str = ET.tostring(front, encoding='utf-8').decode()
            
            with open(temp_template, "r", encoding="utf-8") as f:
                template_content = f.read()
            
            front_start = template_content.find("<front>")
            front_end = template_content.find("</front>")
            
            if front_start == -1 or front_end == -1:
                st.error("Template does not contain <front> tags")
                return
            
            combined_content = (
                template_content[:front_start] +
                xml_str +
                template_content[front_end + len("</front>"):]
            )
            
            st.session_state.final_combined_xml = combined_content
            st.success("XML successfully combined with template!")
            
            with st.expander("Preview Combined XML Output"):
                st.code(combined_content, language="xml")
    except Exception as e:
        st.error(f"Error combining with template: {str(e)}")
    finally:
        if os.path.exists(temp_template):
            os.remove(temp_template)

def main():
    st.title("Journal Article XML Generator")
    st.markdown('<div style="font-size:18px;margin-bottom:10px; font-weight:600">This tool creates JATS XML by merging metadata from the article PDF and web input with back-section content from Vertopal.</div>', unsafe_allow_html=True)
    
    # Main XML Processing Form
    st.markdown("---")
    reset_key = st.session_state.reset_counter
    
    with st.form("input_form"):
        st.markdown('<div style="font-size:25px; font-weight:600; margin-bottom:10px;">Upload PDF File</div>', unsafe_allow_html=True)
        pdf_file = st.file_uploader(
            " ",
            type=['pdf'], 
            help="Upload the article PDF file",
            key=f"pdf_uploader_{reset_key}",
            label_visibility="collapsed"
        )
        
        st.markdown('<div style="font-size:25px; font-weight:600; margin-bottom:10px;">Upload Input XML File</div>', unsafe_allow_html=True)
        input_xml = st.file_uploader(
            " ",
            type=['xml'], 
            help="Upload the original XML metadata file",
            key=f"xml_uploader_{reset_key}",
            label_visibility="collapsed"
        )
        
        st.markdown('<div style="font-size:25px; font-weight:600; margin-bottom:-30px;">Article URL</div>', unsafe_allow_html=True)
        article_url = st.text_input(
            label=" ",
            help="Enter the URL of the article webpage", 
            key=f"article_url_{reset_key}",
            value=""
        )

        st.markdown('<div style="font-size:25px; font-weight:600; margin-bottom:-30px;">PDF Link</div>', unsafe_allow_html=True)
        pdf_link = st.text_input(
            label=" ", 
            help="Enter the direct URL to the PDF file", 
            key=f"pdf_link_{reset_key}",
            value=""
        )
        
        st.write("")
        
        col1, col2 = st.columns([1, 4])
        with col1:
            reset_button = st.form_submit_button("Reset", type="secondary")
        with col2:
            submit_button = st.form_submit_button("Generate XML", type="primary")

        if reset_button:
            clear_form()
            st.rerun()
            
        if submit_button:
            if not all([pdf_file, input_xml, article_url]):
                st.warning("Please provide all required files and URLs")
            else:
                process_files(pdf_file, input_xml, article_url, pdf_link)
    
    if st.session_state.show_combine_section:
        st.markdown("---")
        st.markdown('<div style="font-size:25px; font-weight:600; margin-bottom:10px;">Combine with Template XML</div>', unsafe_allow_html=True)
        
        with st.form("template_form"):
            template_file = st.file_uploader(
                "Upload Template XML",
                type=['xml'],
                help="Upload the template XML file to combine with (must contain <front> section)",
                key=f"template_uploader_{reset_key}"
            )
            
            combine_button = st.form_submit_button("Combine with Template")
            
            if combine_button:
                if template_file is None:
                    st.warning("Please upload a template XML file")
                else:
                    combine_with_template(template_file)
    
    if st.session_state.processed_xml:
        st.download_button(
            label="Download Processed XML",
            data=st.session_state.processed_xml,
            file_name=st.session_state.filename,
            mime="application/xml",
            key="processed_download"
        )
    
    if st.session_state.final_combined_xml:
        st.download_button(
            label="Download Combined XML",
            data=st.session_state.final_combined_xml,
            file_name=st.session_state.filename,
            mime="application/xml",
            key="combined_download"
        )
    
    if st.session_state.show_success:
        st.success("All inputs have been cleared!")
        st.session_state.show_success = False

if __name__ == "__main__":
    main()






