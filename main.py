# -*- coding: utf-8 -*-
import requests
import openai
import json
import time


# ===================== 1. 输入 Cookie / Token 信息 ===========================

SESSDATA = input("请输入你的 B 站 SESSDATA: ").strip()
BILI_JCT = input("请输入你的 B 站 bili_jct: ").strip()
DEDEUSERID = input("请输入你的 B 站 DedeUserID: ").strip()
default_base_url = "https://openai.com/v1"
default_system_prompt = """
你是一个返回 JSON 的助手和音乐类视频选择助手。你**必须**只输出JSON，不要多余解释。
给你若干歌曲及对应的 B 站搜索结果，请你根据视频标题和相关信息，为每首歌选出音质最高，质量最高、音乐匹配的一条视频（每个视频含标题、bvid、点赞数、播放数、收藏数。默认排序位置就是给你的顺序）。
选择时需考虑顺序重要性依次排序为：
是否为高质量分享或音乐歌单的视频（无损、Hires等）
尽量选择歌单形式或优质音乐分享的视频，以提供更舒适的歌曲试听体验。
收藏数 ，点赞数， 播放数指标，其中收藏数最重要；
不用执着于官方等关键词，意义不大；且给出的原始顺序没有任何意义
你需要给出解释。输出格式示例：
[
  {"song_index":0,"bvid":"BVxxx...", "title":"xxx", "reason":"xxx"},
  {"song_index":1,"bvid":"BVxxx...", "title":"xxx", "reason":"xxx"},
  ...
]
"""
# ===================== 2. 获取 QQ 音乐歌单 URL ===========================
print("\n现在请输入 QQ 音乐歌单页面的 URL")
print("例如: https://y.qq.com/n/ryqq/playlist/8764695552\n")
playlist_url = input("请输入 URL: ").strip()

import re
import requests

def fetch_song_list_from_url(url):
    """
    根据 QQ 音乐歌单 URL，爬取歌单信息。
    返回一个列表，每个元素是一个字典，包含 'artist' 和 'name' 两个键。
    """
    # 第一步：从URL里提取 disstid
    match = re.search(r'playlist/(\d+)', url)
    if not match:
        print("错误：未能从 URL 中提取到 playlist ID")
        return []
    disstid = match.group(1)

    # 第二步：构造 QQ 音乐官方接口的请求
    api_url = "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg"
    params = {
        "type": "1",
        "json": "1",
        "utf8": "1",
        "onlysong": "0",
        "new_format": "1",
        "disstid": disstid,
        "format": "json"
    }

    # 适度添加请求头，模拟浏览器访问
    headers = {
        "referer": "https://y.qq.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) \
                       AppleWebKit/537.36 (KHTML, like Gecko) \
                       Chrome/90.0.4430.85 Safari/537.36"
    }

    try:
        response = requests.get(api_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # 第三步：从 JSON 中找到歌单信息
        cdlist = data.get("cdlist", [])
        if not cdlist:
            print("错误：API 返回数据里未找到 cdlist")
            return []
        
        songlist = cdlist[0].get("songlist", [])
        if not songlist:
            print("错误：API 返回数据里未找到 songlist")
            return []

        # 第四步：组织返回结果
        results = []
        for song in songlist:
            name = song.get("title", "").strip()
            # 可能有多个歌手，用 "/" 连接
            singers = song.get("singer", [])
            artist = " / ".join(s.get("name", "") for s in singers)
            results.append({"artist": artist, "name": name})

        return results

    except Exception as e:
        print(f"获取歌单失败: {e}")
        return []



# ================ 4. B 站搜索、收藏等 API (整合到本文件中) ===================
def search_bilibili_video(keyword):
    """
    在哔哩哔哩上搜索视频，返回形如:
    [
      {'title': 'xxx', 'bvid': 'BVxxxx'},
      ...
    ]
    可能抛出异常，或返回空列表
    """
    search_url = "https://api.bilibili.com/x/web-interface/wbi/search/type"
    params = {
        "search_type": "video",
        "keyword": keyword,
        "page": 1,
        "tids": 0,
        "duration": 0,
        "order": "totalrank",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/",
        "Cookie": "SESSDATA=xxx;",
    }
    resp = requests.get(search_url, params=params, headers=headers)
    resp.raise_for_status()

    results = []
    try:
        data = resp.json()

        if data["code"] == 0 and data["data"]["numResults"] > 0:
            for item in data["data"]["result"]:
                results.append(
                    {
                        "title": item["title"].replace(
                            '<em class="keyword">', ""
                        ).replace("</em>", ""),
                        "bvid": item["bvid"],
                        "like": item["like"],
                        "play": item["play"],
                        "favorite": item["favorites"],
                    }
                )
    except Exception as e:
        print(f"解析搜索结果失败: {resp.text}")
        return []

    return results


def bvid_to_avid(bvid):
    """
    将 bvid 转换为 avid
    """
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        j = r.json()
        if j["code"] == 0:
            return j["data"]["aid"]
    except:
        pass
    return None


def add_video_to_favorites(avid, fav_id, sessdata, bili_jct, dedeuserid):
    """
    将视频添加到哔哩哔哩收藏夹
    """
    add_url = "https://api.bilibili.com/x/v3/fav/resource/deal"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.bilibili.com/",
        "Cookie": f"SESSDATA={sessdata}; bili_jct={bili_jct}; DedeUserID={dedeuserid};",
    }
    data = {
        "rid": avid,
        "type": 2,
        "add_media_ids": fav_id,
        "csrf": bili_jct,
    }
    resp = requests.post(add_url, headers=headers, data=data)
    try:
        js = resp.json()
        if js["code"] == 0:
            print(f"视频 {avid} 已成功添加到收藏夹 {fav_id}")
            return True
        else:
            print(f"添加视频到收藏夹失败: {js.get('message')}")
            return False
    except:
        print(f"解析添加收藏夹结果失败: {resp.text}")
        return False


# =============== 5. 调用 LLM 做筛选的函数 ===============
def call_llm_for_best_video(song_info_list, openai_api_key, base_url, system_prompt):
    """
    根据每首歌搜索到的多条视频结果，通过 LLM 选出最匹配的一条 (bvid)。
    如果无合适结果，则返回 None。
    返回列表 best_bvids 与 song_info_list 对应：best_bvids[i] 即第 i 首歌的 bvid (或 None)。
    """
    client = openai.OpenAI(
        api_key=openai_api_key,
        base_url=base_url
    )
    user_content = {
        "songs": [],
    }

    for i, info in enumerate(song_info_list):
        user_content["songs"].append(
            {
                "song_index": i,
                # "song": info["song"],
                "search_results": info["search_results"],
            }
        )

    try:
        messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
            ]
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            stream=True,
        )
        # reply = response.choices[0].message.content.strip()
        collected_messages = []
        for chunk in response:
            chunk_message = chunk.choices[0].delta #.content  # 获取增量内容
            if chunk_message.content is not None:
                collected_messages.append(chunk_message)

        reply = ''.join([m.content for m in collected_messages])

        # full_reply = response.choices[0].message.content.strip()
        print("LLM 完整输入和响应: ", reply)
        print("=====================================> <=====================================")
        try:
            # 去除可能的前缀、后缀，以及首尾空格
            reply = reply.strip()
            if reply.startswith("```json"):
                reply = reply[7:]
            if reply.endswith("```"):
                reply = reply[:-3]
            reply = reply.strip()

            # 尝试直接解析
            data = json.loads(reply)
        except json.JSONDecodeError:
            # 如果直接解析失败，尝试修复 JSON 字符串
            try:
                # 尝试用正则表达式提取 JSON 数组部分
                import re
                match = re.search(r"\[.*\]", reply, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                else:
                    raise ValueError("无法提取 JSON 数组")
            except Exception as e:
                print(f"JSON 修复失败: {e}")
                return [None] * len(song_info_list)

        # 验证数据格式
        if not isinstance(data, list):
            print("LLM 返回的不是数组格式")
            return [None] * len(song_info_list)

        # 构造返回列表 best_bvids和 best_titles
        best_bvids = [None] * len(song_info_list)
        best_titles = [None] * len(song_info_list)
        for item in data:
            if not isinstance(item, dict):
                continue
            idx = item.get("song_index")
            bvid = item.get("bvid")
            title = item.get("title")
            if isinstance(idx, int) and 0 <= idx < len(song_info_list):
                best_bvids[idx] = bvid
                best_titles[idx] = title

        # 打印选择结果
        print("\n视频选择结果:")
        for i, (btt, info) in enumerate(zip(best_titles, song_info_list)):
            song_name = f"{info['song']['artist']} - {info['song']['name']}"
            print(f"歌曲 {i+1}: {song_name} -> {btt or '未找到匹配视频'}")

        return best_bvids

    except Exception as e:
        print(f"调用 LLM 选视频出错: {e}")
        import traceback
        traceback.print_exc()
        return [None] * len(song_info_list)

# ==================== 6. 主流程：搜索 -> LLM选 -> LLM查重 -> 收藏 ===============
def main():
    # 问用户要收藏夹ID
    fav_id = input("\n请输入要使用的收藏夹ID(如 3356761953): ").strip()
    if not fav_id:
        print("未输入收藏夹ID，程序结束。")
        return

    # 问用户要OpenAI key
    openai_api_key = input("\n请输入你的OpenAI API Key(示例: sk-xxx): ").strip()
    if not openai_api_key:
        print("未输入OpenAI API Key，程序结束。")
        return

    # 获取 QQ 音乐歌单并解析
    songs = fetch_song_list_from_url(playlist_url)
    if not songs:
        print("未能获取到任何歌曲，程序结束。")
        return
    print(f"\n共获取到 {len(songs)} 首歌，将开始搜索并调用 LLM 判断最佳视频...\n")
    
    # 调用 LLM，选出最佳视频
    custom_base_url = input(f"\n请输入自定义的 base_url (留空使用默认值: {default_base_url}): ").strip()
    base_url = custom_base_url if custom_base_url else default_base_url

    custom_system_prompt = input(f"\n请输入自定义的 system_prompt (留空使用默认值):\n{default_system_prompt}\n").strip()
    system_prompt = custom_system_prompt if custom_system_prompt else default_system_prompt
        
    batch_size = input("请输入每批处理的歌曲数量(不要超过30，否则会报错): ").strip()
    try:
        batch_size = int(batch_size)
        if batch_size > 30:
            print("输入超过30，默认使用20。")
            batch_size = 20
    except ValueError:
        print("输入无效，默认使用20。")
        batch_size = 20
    for i in range(0, len(songs), batch_size):
        batch_songs = songs[i:i + batch_size]
        print(f"\n处理第 {i + 1} 到 {i + len(batch_songs)} 首歌...\n")
        
        # 搜索计数、失败计数
        fail_count = 0
        success_count = 0

        # 收集搜索结果
        song_info_list = []
        for song in batch_songs:
            keyword = f"{song['name']} {song['artist']}"
            try:
                videos = search_bilibili_video(keyword.replace("/", " "))
                if videos:
                    success_count += 1
                else:
                    fail_count += 1
                song_info_list.append(
                    {"song": song, "search_results": videos}
                )
                print(f"搜索《{keyword}》完成, 找到{len(videos)}条视频.")
            except Exception as e:
                print(f"搜索《{keyword}》出现异常: {e}")
                fail_count += 1
                song_info_list.append({"song": song, "search_results": []})

            # 如果失败次数过多，提示重输Cookie
            if fail_count >= 3:
                print("\n搜索失败次数过多，可能是Cookie失效或网络问题，需重新输入 SESSDATA / bili_jct / DedeUserID.\n")
                new_sessdata = input("新的 SESSDATA: ").strip()
                new_bili_jct = input("新的 bili_jct: ").strip()
                new_dedeuserid = input("新的 DedeUserID: ").strip()
                if new_sessdata and new_bili_jct and new_dedeuserid:
                    globals()["SESSDATA"] = new_sessdata
                    globals()["BILI_JCT"] = new_bili_jct
                    globals()["DEDEUSERID"] = new_dedeuserid
                    print("已更新Cookie，继续执行。")
                    fail_count = 0
                else:
                    print("未完整输入，直接继续")
                    break

        best_bvids = call_llm_for_best_video(song_info_list, openai_api_key, base_url, system_prompt)
        # 整理最终要收藏的 { "title": ..., "bvid": ... } 列表
        new_videos_for_check = []
        for info, bvid in zip(song_info_list, best_bvids):
            if bvid is None:
                continue
            title_for_bvid = None
            for vs in info["search_results"]:
                if vs["bvid"] == bvid:
                    title_for_bvid = vs["title"]
                    break

            if not title_for_bvid:
                title_for_bvid = f"视频_{bvid}"
            new_videos_for_check.append(
                {
                    "song": info["song"],     # 保留一下
                    "chosen_bvid": bvid,
                    "chosen_title": title_for_bvid,
                }
            )

        if not new_videos_for_check:
            print("没有任何可收藏的视频，程序结束。")
            return

        # 逐个收藏
        for item in new_videos_for_check:
            avid = bvid_to_avid(item["chosen_bvid"])
            if not avid:
                print(f"bvid 转 avid 失败，跳过: {item['chosen_bvid']}")
                continue

            ok = add_video_to_favorites(avid, fav_id, SESSDATA, BILI_JCT, DEDEUSERID)
            if ok:
                song_desc = f"{item['song']['artist']} - {item['song']['name']}"
                print(f"已添加歌曲《{song_desc}》对应视频到收藏夹。")
                # 防止过快被风控
                time.sleep(0.8)
        # 等待10秒
        print("\n等待5秒后继续处理下一批歌曲...\n")
        time.sleep(5)
    print("\n全部处理结束。")


if __name__ == "__main__":
    main()
