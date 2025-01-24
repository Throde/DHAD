from bs4 import BeautifulSoup
import re
import os

BASE_FOLDER = "" # 会自动提取更新，无需手动填充

# =====================
# 核心功能函数
def remove_nontext(soup):
    """删除所有非正文元素（表格、图片）"""
    # 1. 删除所有表格
    for table in soup.find_all('table'):
        table.decompose()
    # 2. 删除所有图片
    for img in soup.find_all('img'):
        img.decompose()
    
def remove_citations(soup):
    """删除所有文内引用"""

    def label_apa_citation_group(a_tag):
        """已知是APA格式引用，给定一个右不封闭的<a>，检查后续是否有<a>可以封闭引用"""
        # 用于检查连续多引用：如(Siemens et al., 2011a, Stokols, 2006, Wilson, 1996)
        # 继续查找后续的 <a> 标签，直到找到右括号结尾
        follow_parts = []
        next_tag = a_tag.find_next_sibling()
        while next_tag and (
            (next_tag.name=='a' and not next_tag.get_text(strip=True).endswith(')')) or (not next_tag.get_text(strip=True))
            ):
            # 有两种情况都要继续向后检测：下一个元素为<a>且仍未封闭，或者下一个元素不为<a>但是是空元素
            follow_parts.append(next_tag)
            next_tag = next_tag.find_next_sibling()
        # 如果最后找到以 ")" 结尾的 <a> 标签，则括号成功封闭
        if next_tag and next_tag.name=='a' and next_tag.get_text(strip=True).endswith(')'):
            follow_parts.append(next_tag)
            # 给所有后续 <a> 标签添加 class="decompose"
            for tag in follow_parts:
                tag['class'] = tag.get('class', []) + ['decompose']
            return True
        return False

    for a_tag in soup.find_all('a', href=True):

        # 0. 特殊：如果已在前序元素的处理中被标记删除，则直接删除即可
        if 'decompose' in a_tag.get('class', []):
            a_tag.decompose()
            continue

        # 1. 引用格式1：<sup>上标类型的文内引用
        if a_tag.find('sup'):
            # 获取主文本
            previous_text = a_tag.find_previous('span').text
            # 获取<sup>前的文本
            for sup_tag in a_tag.find_all('sup'):
                sup_tag.decompose()
            text_to_add = a_tag.get_text()
            # 将挂载<sup>的内容合并至前面的主文本中
            a_tag.find_previous('span').string = previous_text+text_to_add
            # 删除整个<a>标签
            a_tag.decompose()
            continue

        # 2. 引用格式2：[9]方括号类型的文内引用
        # 确保 <a> 标签的 href 属性以 "#bookmark" 开头
        if a_tag['href'].startswith('#bookmark'):
            # 获取 <a> 标签中的文本
            a_text = a_tag.get_text(strip=True)
            # 检查文本中是否包含方括号中的数字，例如 [9]
            if re.search(r'\[\d+\]', a_text):
                # 检查是否带页数：不以 ")" 结尾，且下一元素以数字开头，则先将后续的页数给删掉
                if not a_text.endswith(')') and a_tag.find_next_sibling('span'):
                    next_span = a_tag.find_next_sibling('span')
                    span_text = next_span.get_text(strip=True)
                    if re.search(r'^\d+\)', span_text):
                        # 删除后续的页数部分，例如 "133)"
                        new_text = re.sub(r'^\d+\)', '', span_text)
                        next_span.string = new_text
                a_tag.decompose()
                continue

        # 3. 引用格式3：(author, year) APA格式的文内引用
        # 确保 <a> 标签的 href 属性以 "#bookmark" 开头
        if a_tag['href'].startswith('#bookmark'):
            # 确保 <a> 标签的文本内容以圆括号开头和结束
            a_text = a_tag.get_text(strip=True)
            if re.match(r'^\(.*\)$', a_text):  # 若以圆括号开头和结束
                # 删除整个 <a> 标签及其内容
                a_tag.decompose()
                continue
            elif a_text.startswith('('): # 否则，若只以圆括号开头
                # 继续查找后续的 <a> 标签，直到找到右括号结尾
                if label_apa_citation_group(a_tag):
                    # 成功找到一组，删除当前标签（后续<a>也已在函数中标记class='decompose'）
                    a_tag.decompose()
                    continue

def remove_bibliography(soup):
    """删除所有文末文献"""
    # 定义要匹配的文本内容
    target_texts = [
        'Bibliography', 'References', 'Reference', 'References and Resources', 
        'Works cited', 'Works consulted', 
        'Acknowledgements','Acknowledgments', 'Acknowledgment', 
        'Funding', 'Declarations', 'End Notes', 'Endnotes', 'Endnote', 'Notes', 
        'Competing Interest', 'Competing Interests', 
        'Editorial Contributions', 'Index of cited projects'
    ]
    # 转换目标关键词为小写，便于无视大小写匹配
    target_texts = [text.lower() for text in target_texts]
    
    def cap_ok(tag):
        """用于判断给定标签在大小写上是否符合成为小标题的要求"""
        # 显示地，首字母大写符合要求
        if tag.get_text(strip=True)[0].isupper():
            return True
        # 否则，实际文本小写，但是style将之渲染为大写也可
        if tag.find('span') and 'style' in tag.find('span').attrs:
            style_value = tag.find('span')['style'] # 获取 style 属性的值
            if 'font-variant:small-caps;' in style_value:
                return True
        return False

    # 遍历所有 <p> 元素
    for p_tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        p_text = p_tag.get_text(strip=True)
        # 去除末尾的冒号 (:) 句点 (.) 星号 (*) 以兼容带这3种符号的情况
        p_text = re.sub(r'[:\.\*]+$', '', p_text).lower()  # 转为小写以无视大小写匹配
        # 如果 <p> 的文本是我们要删除的关键词之一（且首字母必须为大写以避免误删正文）
        if p_text in target_texts and cap_ok(p_tag):
            # 删除后续所有元素
            for next_p_tag in p_tag.find_all_next():
                next_p_tag.decompose()
            # 当前 <p> 元素也一并删除
            p_tag.decompose()
            return True # 成功找到并处理，返回True
    
    return False # 如果此法没有找到符合条件的 <p> 元素，返回False以警示

def remove_small_font(soup, thresh=7):
    """删除字号过小的元素（一般是非正文），同时简化<style>代码"""
    # 1. 查找所有 <style> 标签
    small_font_classes = [] # 保存属于过小字号的 font 类名
    for style_tag in soup.find_all('style'):
        # 获取style标签中的CSS文本
        css_text = style_tag.string
        if css_text:
            new_css_lines = []  # 按行分割CSS文本
            for line in css_text.splitlines():
                if '.font' in line:  # 只保留包含 .font 类规则
                    # 查找字号小于等于阈值（7pt）的字体类
                    match = re.search(r'\.font(\d+) \{ font:(\d+)pt', line)
                    if match and int(match.group(2)) <= thresh:
                        # 字号过小，需要删除，而不加回 <style> 中
                        small_font_classes.append(f'.font{match.group(1)}')
                    else:
                        # 字号正常，保留回 <style> 中
                        new_css_lines.append(line.strip())
            # 将筛选后的CSS规则更新回style标签
            style_tag.string = "\n" +"\n".join(new_css_lines) +"\n"

    # 2. 遍历所有具有相关 font class 的元素并删除
    for font_class in small_font_classes:
        for element in soup.find_all(class_=font_class[1:]):  # 去掉 .font 开头
            element.decompose()

def remove_trivial_p(soup):
    """删除琐碎的<p>元素"""
    # 定义一系列工具函数
    def is_special_punctuation(text):
        """用于判断文本是否包含特殊标点符号"""
        # 特殊标点符号定义为：非字母、非数字的符号，排除空格
        return all(not char.isalnum() and char not in ' ' for char in text)
    
    def only_contain_urls(p):
        """查看是否仅包含链接"""
        # 遍历 <p> 的所有直接子元素
        for child in p.children:
            # 如果子元素是 <a href="http..."> 或其他类型的空元素（无可见文本），均可删除
            if (child.name == 'a' and child.has_attr('href') and child['href'].startswith('http')) or (child.name != 'a' and (not child.get_text(strip=True))):
                continue
            else:
                # 一旦查到含有不可删除的内容，则返回False
                return False
        return True
    
    def is_copyright_line(text):
        """检查是否为版权行"""
        # 版权格式1： "cb yyyy."开头（如 "cb 2019."）
        if re.search(r'^cb ?\d{4}\.', text):
            return True
        # 版权格式2：同时包含 "©" 和 "yyyy" 年份的行（如 "Copyright © 2024 ..." 和 "Published online: 9 February 2019 © The Author(s) 2019"）
        if '©' in text and re.search(r'\d{4}', text):
            return True
        return False
    
    # 遍历所有 <p> 元素
    for p in soup.find_all('p'):
        # 获取 <p> 下的所有文本内容（去除前后空格）
        p_text = p.get_text(strip=True)
        
        # 1.删除<p>: 包含<a href="mailto:xxx">的（一般是作者信息）
        if p.find('a', href=re.compile(r'^mailto:')):
            p.decompose()
            continue
        # 2.删除<p>: 数字单独成行的
        if p_text.isdigit():
            p.decompose()
            continue
        # 3.删除<p>: 纯特殊标点符号组成的
        if is_special_punctuation(p_text):
            p.decompose()
            continue
        # 4.删除<p>: 论文的 DOI号 和 ISSN号 
        if p_text.startswith('DOI:') or p_text.startswith('ISSN:'):
            p.decompose()
            continue
        # 5.删除<p>: 版权行
        if is_copyright_line(p_text):
            p.decompose()
            continue
        # 6. 删除 <p>: 仅包含 <a href="http..."> 网页链接而无其他正文的
        if only_contain_urls(p):
            p.decompose()
            continue

def simplify_elements(soup):
    """精简元素：删除所有空元素（没有文本内容），并合并相邻的同字号<span>元素、合并原本属于同一段的<p>"""
    # 1. 删去空元素
    for tag in ['span', 'ul', 'p', 'div', 'a', 'br']:
        for element in soup.find_all(tag):
            if not element.get_text(strip=True):
                element.decompose()
    
    # 2. 合并相邻可合并的 <span> 元素
    for span in soup.find_all('span', class_=True):  # 只处理有class的<span>
        next_span = span.find_next_sibling()  # 查找下一个兄弟 <span> 元素
        if next_span and next_span.name=='span' and span['class'] == next_span['class']:  # 检查 class 是否相同
            # 合并两个 <span> 元素的文本内容
            next_span.string = (span.get_text() + next_span.get_text())
            # 删除当前的 <span> 元素
            span.decompose()

    # 3. 删除所有剩余元素标签中的style属性
    for tag in soup.find_all(True):
        if tag.has_attr('style'):
            del tag['style']

    # 4. 合并相邻的<p>元素：检查是否符合：1.无终结标点 2.下一个<p>的小写字母开头 3.字体相同
    for p_tag in soup.find_all('p'):
        # 判断当前 <p> 是否没有终结标点符号
        p_text = p_tag.get_text(strip=True)
        if not re.search(r'[.!?]$', p_text):  # 如果没有句号、感叹号或问号结尾
            # 判断下一个 <p> 是否以小写字母开头
            next_p_tag = p_tag.find_next_sibling('p')
            if next_p_tag and next_p_tag.get_text(strip=True)[0].islower():
                # 初步判断应将二者合并。继续检查头尾<span>的字号是否相同
                # 获取当前 <p> 的最后一个子<span> 
                last_span = p_tag.find_all('span', class_=True)[-1] if p_tag.find_all('span', class_=True) else None
                # 获取下一个 <p> 的第一个子<span>
                next_span = next_p_tag.find_all('span', class_=True)[0] if next_p_tag.find_all('span', class_=True) else None
                # 检查字号属性
                if last_span and next_span and last_span['class'] == next_span['class']:
                    # 先插入一个空格
                    next_span.insert(0, " ")
                    # 将当前 <p> 标签的所有子元素插入到下一个 <p> 标签的前面，保持顺序
                    for child in reversed(list(p_tag.children)):
                        next_p_tag.insert(0, child)  # 将当前 <p> 的子元素插入到下一个 <p> 标签的前面
                    # 删除当前 <p> 元素
                    p_tag.decompose()

# =====================
# 处理主流程
def clean_html(input_file, output_dir):
    # 读取原HTML文件内容
    with open(input_file, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')
    
    # 1. 删除所有表格元素
    remove_nontext(soup)

    # 2. 删除所有引用
    remove_citations(soup)
    bib_removed = remove_bibliography(soup)
    if not bib_removed:
        print(f"[!] 未检索到文末板块：{truncate_path(input_file)}")

    # 3. 删除字号过小的<span>元素（一般是图片识别出的字、注释等）
    remove_small_font(soup)

    # 4. 删除琐碎的<p>元素（一般是页码、版权©声明、作者邮箱等）
    remove_trivial_p(soup)

    # 4. 精简、合并处理后的HTML元素
    simplify_elements(soup)
    # 将 HTML 转为字符串去掉空行
    html_content = str(soup)
    html_content = "\n".join([line for line in html_content.splitlines() if line.strip()])
    
    # 将处理后的HTML另存为新文件
    # output_file = input_file.replace('.htm', '_clean.html') # 直接生成在旁边
    output_file = os.path.join(output_dir, os.path.basename(input_file).replace('.htm', '.html'))
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write(html_content)

    # print(f"处理完成：{output_file}")

def truncate_path(full_path):    
    # 找到 BASE_FOLDER 开始的路径部分
    path_parts = full_path.split(os.sep)  # 使用 os.sep 来分割路径（平台独立）
    for i, part in enumerate(path_parts):
        if part == BASE_FOLDER:
            # 从 BASE_FOLDER 开始的路径部分之后的内容
            truncated_path = os.sep.join(path_parts[i+1:])
            return truncated_path
    # 若没找到，则原样返回
    return full_path

def process_all_htm_files():
    # 获取当前目录
    current_dir = os.getcwd()
    print(">>> 当前处理：", current_dir)
    global BASE_FOLDER
    BASE_FOLDER = current_dir.split(os.sep)[-1] # 获取当前执行操作的总文件夹名，用于后续简化 print() 输出的内容
    # 统计处理的文件数
    total_files_processed = 0
    # 遍历当前目录及其子目录下的所有文件
    for dirpath, dirnames, filenames in os.walk(current_dir):
        for filename in filenames:
            # 如果文件是 .htm 格式
            if filename.endswith('.htm'):
                input_file = os.path.join(dirpath, filename)

                # 创建新的输出目录（副本目录）
                relative_path = os.path.relpath(dirpath, current_dir)  # 获取相对路径
                output_dir = os.path.join(current_dir, f"{os.path.basename(current_dir)}_clean", relative_path)

                # 确保输出目录存在
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)

                clean_html(input_file, output_dir)
                total_files_processed += 1

    # 汇报处理的总数
    print(f"> 总共处理了 {total_files_processed} 个 .htm 文件。")

if __name__=="__main__":
    # 调用函数，传入原始HTML文件路径
    # input_file = 'mcsuccurro,+18260-Carnevali+et+al.htm'  # 替换成你的文件名
    # clean_html(input_file)

    process_all_htm_files()
    