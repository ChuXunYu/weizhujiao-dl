import os
import time
import requests
import random
from urllib.parse import urlparse, unquote, quote
from dotenv import load_dotenv # <--- 新增导入

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- 从 .env 文件加载环境变量 ---
load_dotenv()

# --- 从环境变量中读取配置 ---
COURSE_LIST_URL = os.getenv("COURSE_LIST_URL")
COURSE_BUTTON_LOCATOR_XPATH = os.getenv("COURSE_BUTTON_LOCATOR_XPATH")

# 检查环境变量是否成功加载
if not COURSE_LIST_URL or not COURSE_BUTTON_LOCATOR_XPATH:
    print("错误：请确保 .env 文件存在于脚本相同目录下，")
    print("并且其中包含 COURSE_LIST_URL 和 COURSE_BUTTON_LOCATOR_XPATH 变量。")
    exit()

# --- 主程序 ---

def setup_driver():
    """初始化并返回一个Chrome WebDriver实例"""
    print("正在设置浏览器驱动...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service)
    driver.implicitly_wait(5)
    return driver

def try_fix_url(url, expected_filename):
    """尝试根据期望的文件名修复URL中的文件名部分，并正确处理URL编码
    
    Args:
        url: 原始URL（可能已被错误解码）
        expected_filename: 期望的文件名
    
    Returns:
        修复后的URL（正确编码）
    """
    if not expected_filename:
        return url
    
    # 从URL中提取基础部分和文件名部分
    # 例如: https://app.teachermate.com.cn/9cdLn-1693370741604-Chapter One From C to C .ppt
    # 分解为: https://app.teachermate.com.cn/ + 9cdLn-1693370741604- + Chapter One From C to C .ppt
    
    try:
        # 找到最后一个 '-' 之前的部分
        last_dash_idx = url.rfind('-')
        if last_dash_idx > 0:
            # 获取URL的前缀部分（包含ID）
            prefix = url[:last_dash_idx + 1]
            
            # 从期望文件名中提取实际文件名（去掉前面的K编号）
            # 例如: K0002-1-1 Chapter One From C to C++.ppt -> Chapter One From C to C++.ppt
            filename_parts = expected_filename.split()
            actual_filename = None
            for i, part in enumerate(filename_parts):
                if not part.startswith('K') or i > 0:
                    actual_filename = ' '.join(filename_parts[i:])
                    break
            
            if actual_filename:
                # 正确编码文件名：
                # 1. 先对整个文件名进行URL编码（+会变成%2B）
                # 2. 然后将%20替换为+（这是URL中空格的标准表示）
                encoded_filename = quote(actual_filename, safe='.')
                # 将空格的编码%20替换为+
                encoded_filename = encoded_filename.replace('%20', '+')
                
                # 构建新的URL
                fixed_url = prefix + encoded_filename
                return fixed_url
    except Exception as e:
        print(f"    URL修复失败: {e}")
    
    return url

def download_file(session, url, headers, directory=".", expected_filename=None):
    """使用requests库下载文件
    
    Args:
        session: requests会话对象
        url: 下载链接
        headers: 请求头
        directory: 保存目录
        expected_filename: 期望的文件名（从课件名称中提取），如果提供则优先使用
    """
    try:
        # 如果提供了期望的文件名，使用它；否则从URL中提取
        if expected_filename:
            meaningful_name = expected_filename
            print(f"准备下载文件: {meaningful_name} (使用课件原始名称)")
        else:
            path = urlparse(url).path
            filename = unquote(os.path.basename(path))
            clean_filename = filename.split('?')[0]
            
            try:
                meaningful_name = clean_filename.split('-')[-1]
            except:
                meaningful_name = clean_filename
            
            print(f"准备下载文件: {meaningful_name}")
        
        response = session.get(url, stream=True, headers=headers)
        response.raise_for_status()

        filepath = os.path.join(directory, meaningful_name)
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"成功下载并保存文件到: {filepath}\n")
        return True
    except requests.exceptions.RequestException as e:
        # 特别处理403和404错误，重新抛出以便上层捕获
        if e.response is not None and e.response.status_code in [403, 404]:
            raise e # 重新抛出异常
        print(f"下载文件时出错: {e}\n")
        return False
    except Exception as e:
        print(f"处理文件时发生未知错误: {e}\n")
        return False

def main():
    driver = setup_driver()
    
    try:
        print(f"正在访问页面: {COURSE_LIST_URL}")
        driver.get(COURSE_LIST_URL)
        
        # --- 使用从 .env 文件读取的定位符 ---
        course_button_locator = (By.XPATH, COURSE_BUTTON_LOCATOR_XPATH)
        
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(course_button_locator)
        )
        
        user_agent = driver.execute_script("return navigator.userAgent;")
        
        course_buttons = driver.find_elements(*course_button_locator)
        num_courses = len(course_buttons)
        print(f"检测到 {num_courses} 个课件，准备开始处理...")

        session = requests.Session()
        for cookie in driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'])

        for i in range(num_courses):
            course_buttons = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located(course_button_locator)
            )
            button = course_buttons[i]
            
            course_name = button.text.strip().replace('\n', ' ') if button.text.strip() else f"课件 {i+1}"
            print(f"--- 正在处理第 {i+1}/{num_courses} 个课件: {course_name} ---")
            
            # 从课件名称中提取实际文件名（去掉前面的ID和状态标记）
            # 例如："K0002-1-1 Chapter One From C to C++.ppt 已读 Chapter One From C to C++.ppt"
            # 提取最后一个部分作为文件名
            parts = course_name.split()
            # 找到文件扩展名的位置
            expected_filename = None
            for idx, part in enumerate(parts):
                if part.lower().endswith(('.ppt', '.pptx', '.pdf', '.doc', '.docx', '.xls', '.xlsx')):
                    # 从这个位置开始往前找，直到遇到"已读"或"未读"
                    start_idx = 0
                    for j in range(idx, -1, -1):
                        if parts[j] in ['已读', '未读']:
                            start_idx = j + 1
                            break
                    expected_filename = ' '.join(parts[start_idx:idx+1])
                    break
            
            print(f"提取的文件名: {expected_filename}")

            try:
                driver.execute_script("arguments[0].click();", button)
                print("已点击课件按钮，等待操作菜单弹出...")

                preview_button_locator = (By.XPATH, "//span[text()='预览课件']")
                preview_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(preview_button_locator)
                )
                
                driver.execute_script("arguments[0].click();", preview_button)
                print("已点击“预览课件”选项。")
                
                print("正在当前页面寻找预览iframe...")
                iframe_locator = (By.XPATH, "//iframe[contains(@src, 'ow365.cn')]")
                iframe_element = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located(iframe_locator)
                )
                
                ow365_url = iframe_element.get_attribute('src')
                print("成功找到预览URL。")

                modified_url = ow365_url.replace("ssl=1", "ssl=0")
                print("修改URL并正在访问...")
                driver.get(modified_url)
                
                print("正在从页面文本中提取最终下载链接...")
                url_div_locator = (By.CSS_SELECTOR, "div[style='color:red']")
                url_element = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located(url_div_locator)
                )
                
                full_download_link = url_element.text.strip()
                
                headers = { 'User-Agent': user_agent, 'Referer': modified_url }
                
                # ==================================================================
                # vv 最终决定性测试 vv
                # ==================================================================
                
                # 1. 优先尝试直链（删除参数）
                clean_url = full_download_link.split('?')[0]
                print("\n>>> 正在尝试直链（删除参数）下载...")
                print(f"    将要访问的URL: {clean_url}")
                
                try:
                    # 尝试使用无参数的URL下载，并传入期望的文件名
                    download_succeeded = download_file(session, clean_url, headers, expected_filename=expected_filename)
                    if not download_succeeded:
                         # 如果下载失败但不是403，也打印一下信息
                         print("    您指定的方法下载失败，但错误不是403。")

                except requests.exceptions.RequestException as e:
                    # 如果是因为403错误而失败，证明此路不通
                    if e.response is not None and e.response.status_code == 403:
                        print(">>> 正在自动切换到备用方案（保留参数）进行重试...")
                        
                        # 2. 备用方案：使用完整的带有签名参数的URL重试
                        try:
                            download_file(session, full_download_link, headers, expected_filename=expected_filename)
                        except Exception as retry_error:
                            print(f"    备用方案也失败了: {retry_error}")
                    elif e.response is not None and e.response.status_code == 404:
                        # 404错误，尝试修复URL
                        print(">>> 检测到404错误，尝试修复URL...")
                        fixed_url = try_fix_url(clean_url, expected_filename)
                        if fixed_url != clean_url:
                            print(f"    修复后的URL: {fixed_url}")
                            try:
                                download_file(session, fixed_url, headers, expected_filename=expected_filename)
                            except Exception as fix_error:
                                print(f"    修复后的URL仍然无法下载: {fix_error}")
                                print(f"    跳过此文件。")
                        else:
                            print("    无法修复URL，跳过此文件。")
                    else:
                        # 如果是其他网络错误
                        print(f"    您指定的方法下载时遇到未知网络错误: {e}")


            except (TimeoutException, NoSuchElementException) as e:
                print(f"处理课件 '{course_name}' 时出错: {e}")
                print("跳过此课件，继续下一个...")
            
            finally:
                print("正在返回课程列表页面...")
                driver.get(COURSE_LIST_URL)
                
                sleep_time = random.uniform(1, 2)
                print(f"暂停 {sleep_time:.2f} 秒...")
                time.sleep(sleep_time)

    finally:
        print("所有任务已完成，即将关闭浏览器。")
        time.sleep(5)
        driver.quit()

if __name__ == "__main__":
    main()

