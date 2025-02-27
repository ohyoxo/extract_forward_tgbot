"""
tg机器人的所有命令行为
"""
import datetime
from urllib.parse import urlparse
import re
import os, io, sys
import random
import string
import json
import subprocess
import ast
import zipfile
import asyncio
from concurrent.futures import ProcessPoolExecutor

from telegram import Update, Bot
from telegram.ext import ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import error

from process_images import add_text, merge_multi_images, generate_gif, open_image_from_various, merge_images_according_array
from process_video import save_video_from_various, video2gif
from preprocess import config, io4message, io4urlmsg, io4push


# 回复固定内容
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text=f"This is extract-forward bot, 这是一个转存机器人\n\n"
                                        f"基本使用说明：\n"
                                        f"1. 转发(forward)消息给机器人，或者直接发送消息，机器人会存储；\n"
                                        f"2. 发送命令 `\\push` ，会返回网址，访问即可看到所有转发的信息。\n\n"
                                        f"项目地址： https://github.com/AhFeil/extract_forward_tgbot")



def general_logic(update: Update, userid_str: str, line_center_content: str, media_group_id_cache = ["0"]) -> str:
    """通用规则：先提取文本，再把内联网址按顺序列在后面"""
    link = ['']
    
    # 提取内容
    if content := update.message.text:
        search_link = update.message.entities
    elif content := update.message.caption:
        search_link = update.message.caption_entities
        media_group_id_cache[0] = update.message.media_group_id
    else:
        media_group_id = update.message.media_group_id
        if media_group_id in media_group_id_cache:
            # 同一组的图片，不提示错误
            return ""
        else:
            return "not support. 不支持这种消息"
    # 提取内联网址
    for i in search_link:
        link.append(i.url)
    # 有 bug ，对于转发的无内联网址的图片消息，会报错 TypeError: can only concatenate str (not "NoneType") to str 
    # 不理解，发送纯文本又不报错

    # 仅一行且 http 开头的内容，放在 _url 中
    if content and content[0:4] == "http" and '\n' not in content:
        io4urlmsg.append(userid_str, content + '\n')
        reply = "url saved. 保存网址"
    else:
        element = '\n'
        saved_content = '-' * 27 + line_center_content.center(80, '-') + '\n' + content + '\n' + element.join(filter(None, link)) + '\n\n'
        # 保存到文件中
        io4message.append(userid_str, saved_content)
        reply =  "transfer done. 转存完成"
    
    # 同步
    if persistent_webnote_url := config.path_dict.get(userid_str + "_psw"):
        all_stored = io4message.read(userid_str) + "\n\n" + io4urlmsg.read(userid_str)
        push2somewhere = config.push_dir + persistent_webnote_url
        io4push._write(push2somewhere, all_stored)

    return reply


def extract_urls(update: Update):
    # 有时候 AHHH 那个也会发纯文本，如果只有 ~。caption，就不能处理纯文本了，还会报错
    string = ''   # 不然异常终止后会销毁string
    try:
        string += update.message.caption
    except:
        string += update.message.text

    # print(string)
    url = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', string)

    return url


def save_data_of_photos(message, userid_str):
    """自己发送图片或从指定频道转发，将图片的 file_id 和 file_unique_id 存入由 user_ID 区分的队列中"""
    file_id = message.photo[-1].file_id
    file_unique_id = message.photo[-1].file_unique_id
    file_data = (file_unique_id, file_id)
    if config.image_list.get(userid_str):
        config.image_list.get(userid_str).append(file_data)
    else:   # 若没有对应列表，先创建，再添加
        config.image_list[userid_str] = []
        config.image_list[userid_str].append(file_data)

    # 获得说明文字
    userid_text_str = userid_str + "_text"
    try:
        text = message.caption.split("\n", 1)[0]
        config.image_list[userid_text_str] = text
    except:
        text = False   # 失败获取会保留原来的


async def send_gif_file(fileIO: io.BytesIO, file_name: str, user_id: int, context: ContextTypes.DEFAULT_TYPE, del_file_list=[]) -> None:
    """专门发送文件，可选顺便发送原始文件还是压缩包，或都发送，可以避免被压缩。还可传入成功压缩后要删除的文件列表"""
    """暂时只接受 BytesIO 发送"""
    zip_name = file_name + '.zip'
    zip_obj = io.BytesIO()
    with zipfile.ZipFile(zip_obj, mode='w') as zf:
        # 将 BytesIO 对象添加到 ZIP 文件中
        zf.writestr(file_name, fileIO.getvalue())
    try:
        # await context.bot.send_animation(chat_id=update.effective_chat.id, animation=gif_io, filename=image_name)   # 以动画发送会被压缩
        await context.bot.send_document(chat_id=user_id, document=fileIO, filename=file_name)   # 但这个也不行，还是压缩后的
        await context.bot.send_message(chat_id=user_id, text=f"为了防止被 Telegram 压缩(小 gif 会直接转成mp4)，下面发送 zip 压缩包格式")
        # 压缩再发送。直接把 BytesIO 给它，显示空的。先保存再发送倒是可以。 保存压缩包
        temp_zipfile = f"compressed-{user_id}.zip"
        with open(temp_zipfile, "wb") as zip_file:
            zip_file.write(zip_obj.getvalue())
        with open(temp_zipfile, 'rb') as zip_file:
            await context.bot.send_document(chat_id=user_id, document=zip_file, filename=zip_name)
    except error.TimedOut:
        await context.bot.send_message(chat_id=user_id, text="网络超时，未能成功发送，请重新 /image")
    except Exception as e:   # 由于网络不畅会引发一系列异常，光有上面那个，还不够
        print(e)
        await context.bot.send_message(chat_id=user_id, text="可能网络原因，未能成功发送，请重新 /image")
    else:
        os.remove(temp_zipfile)
        for del_file in del_file_list:
            os.remove(del_file)   # 不出意外才删除。发送失败后，下次发送直接使用


def check_file_in_size(file_size_in_bytes, max_in_size):
    """检查文件，防止过大"""
    file_size_in_mb = file_size_in_bytes / (1024 * 1024)

    if file_size_in_mb > max_in_size:
        return False
    else:
        return True


# 转存
async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    userid_str = str(user_id)
    rec_time = (str(datetime.datetime.now()))[5:-7]

    message = update.message
    # 从哪里转发的
    from_yourself = False if message.forward_date else True   # 若消息是自己发送的，则为 True
    from_bot = True if message.forward_from and message.forward_from.username == config.bot_username else False   # 若消息转发自机器人自己发送的，则为 True

    bot = Bot(token=config.bot_token)   # 用于得到文件 URL
    if from_yourself or from_bot:   # 自己发的，肯定是文字就是文字，图片就是图片，有就代表要用那方面的功能，不需要再判断
        line_center_content = rec_time + " from yourself or the bot"
        if message.photo:
            # 如果发送的是图片
            save_data_of_photos(message, userid_str)
        elif message.video:
            # 如果发送的是视频
            file_id = message.video.file_id                     # 一定能复用
            file_unique_id = message.video.file_unique_id
            file_size = message.video.file_size
            if check_file_in_size(file_size, config.video_max_size):   # 文件太大，则不处理
                # 得到视频 URL
                the_file = await bot.get_file(file_id)
                # 转换成 gif
                video_local_path = await save_video_from_various(the_file.file_path, config.store_dir)
                gif_io, gif_path = await video2gif(video_local_path, config.store_dir, (message.video.width, message.video.height), max_width=config.gif_max_width)
                video_name = file_unique_id + ".gif"
                await send_gif_file(gif_io, video_name, user_id, context, del_file_list=[video_local_path, gif_path])
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="文件太大")
                return
        else:
            # 通用规则
            respond = general_logic(update, userid_str, line_center_content)
            if respond:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=respond)
    # 不是自己发的，先根据频道分类，再在频道里细分，调用函数处理。（还可能原生发送人选择隐藏）
    else:
        if chat := message.forward_from_chat:
            channel_title = chat.title
            channel_name = chat.username
            message_id = message.forward_from_message_id
            direct_url = f" https://t.me/{channel_name}/{message_id}"
            line_center_content = rec_time + " from " + channel_title + direct_url
        else:
            channel_name = message.forward_sender_name if message.forward_sender_name else "not hidden_user"
            direct_url = "this message can't be accessed directly"
            line_center_content = rec_time + " from hidden_user" + channel_name + direct_url

        # 对于转发自指定频道的消息进行特殊处理
        if channel_name in config.image_channel:
            # 处理图片和视频的逻辑(若想转存这些频道里带图片的文字，只能手动复制，纯文本可以直接保存)
            if message.photo:
                save_data_of_photos(message, userid_str)
            elif message.video:
                file_id = message.video.file_id
                file_unique_id = message.video.file_unique_id
                file_size = message.video.file_size
                if check_file_in_size(file_size, config.video_max_size):
                    # 得到视频 URL
                    the_file = await bot.get_file(file_id)
                    # 转换成 gif
                    video_local_path = await save_video_from_various(the_file.file_path, config.store_dir)
                    gif_io, gif_path = await video2gif(video_local_path, config.store_dir, (message.video.width, message.video.height), max_width=config.gif_max_width)
                    video_name = file_unique_id + ".gif"
                    await send_gif_file(gif_io, video_name, user_id, context, del_file_list=[video_local_path, gif_path])
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text="文件太大")
                    return
            else:
                respond = general_logic(update, userid_str, line_center_content)
                if respond:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=respond)
        elif channel_name in config.only_url_channel:
            # 只提取网址
            url = extract_urls(update=update)
            io4urlmsg.append(userid_str, '\n'.join(filter(None, url)) + '\n')
            await context.bot.send_message(chat_id=update.effective_chat.id, text='url saved.')
        else:
            respond = general_logic(update, userid_str, line_center_content)
            if respond:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=respond)


async def image_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    指令 /image 调用此函数，这个函数根据用户id，取出其列表里图片id列表和说明文字，合成，然后发给用户
    :return:
    """
    user_id = update.effective_chat.id
    userid_str = str(user_id)
    loop = asyncio.get_event_loop()

    # 都是 作为 key，合成图片的参数
    userid_time_str = userid_str + "_time"
    userid_array_str = userid_str + "_array"
    userid_text_str = userid_str + "_text"
    args = context.args   # 字符串列表
    if args:   # 若存在参数，则不执行 if 代码块下面的内容
        if args[0] == "array":
            # 第一个参数若是 array，代表第二个参数是位置排列的数组
            try:
                actual_tuple = ast.literal_eval(args[1])
            except ValueError:
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text=f"wrong array format, 要像这样 (1,2),(0,3)")
            except SyntaxError:
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text=f"notice blank,brackets , 别有空格，注意括号成对")
            else:
                config.image_option[userid_array_str] = actual_tuple
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text=f"have change array to {actual_tuple}")
        elif args[0] == "time":
            # 第一个参数若是 time，代表第二个参数是 gif 的每个图片持续时间，单位 s
            try:
                actual_duration = ast.literal_eval(args[1])
            except ValueError:
                await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text=f"wrong float format, 可以是整数或带小数点的")
            else:
                if not isinstance(actual_duration, (float, int)):
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"not float or int, 输入整数或带小数点的")
                else:
                    config.image_option[userid_time_str] = actual_duration
                    await context.bot.send_message(chat_id=update.effective_chat.id,
                                                text=f"have change time to {actual_duration}")
        elif args[0] == "clear":
            # 第一个参数若是 clear ，就清空队列里的图片
            config.image_list[userid_str].clear()   # 清空列表
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Have cleared pictures in the queue, 已清空队列里的图片")
        else:
            # 其他任何情况，都只是作为修改说明文字
            text_in_args = args[0]
            config.image_list[userid_text_str] = text_in_args
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"have change text to {text_in_args}")
        return

    # 不带参数则进行合成图片步骤
    duration_time = int(config.image_option.get(userid_time_str, 3) * 1000)   # duration_time = 3000   # 默认 3s
    middle_interval = 10   # 10 个像素
    random_str = ''.join(random.sample(string.ascii_letters + string.digits, 6))
    text = config.image_list.get(userid_text_str, "processed_image" + random_str)
    image_name = text[0:24]   # 以免说明文字太长
    urls_cache = config.urls_cache_dict

    image_id_list = config.image_list.get(userid_str)
    if image_id_list:   # 有且不为空 []
        image_amount = len(image_id_list)   # 图片数量
        # 用于得到图片 URL
        bot = Bot(token=config.bot_token)
        image_url_list = []   # 存有图片网址的列表
        for file_unique_id, file_id in image_id_list:
            # 检查缓存中是否存在图片下载地址
            if file_unique_id in urls_cache.keys():
                url = urls_cache[file_unique_id]
                print(f"{file_unique_id} is in urls_cache")
            else:
                the_file = await bot.get_file(file_id)
                url = the_file.file_path
                # 添加图片下载地址到缓存
                urls_cache[file_unique_id] = url
                # 删除最旧的键值对，如果缓存超过了20条
                if len(urls_cache) > 20:
                    urls_cache.popitem(last=False)
            image_url_list.append(url)
        try:   # 国内开发，有时候网不稳定，下载失败
            img_list = await open_image_from_various(image_url_list, config.images_cache_dict)
        except:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="网络原因，未能下载图片，请重新 /image")
            return

        is_gif = False
        array = config.image_option.get(userid_array_str)
        with ProcessPoolExecutor() as pool:
            if array:   # 如果指定了排列，就按指定的
                array_image_amount = len([i for j in array for i in j if i > 0])
                # 还需要检查是不是从 1 递增的
                if not image_amount == array_image_amount:
                    await context.bot.send_message(chat_id=update.effective_chat.id,
                                                text=f"排列数组里的图片数 {array_image_amount} 与实际图片数 {image_amount} 不一致，请检查")
                # 若数量一致，可调用函数处理
                gif_io = await loop.run_in_executor(pool, merge_images_according_array, img_list, middle_interval, array)
                config.image_option[userid_array_str] = None
            else:   # 根据图片数量，默认的行为
                if image_amount == 1:
                    gif_io = await loop.run_in_executor(pool, add_text, img_list, text)
                elif 1 < image_amount < 5:
                    gif_io = await loop.run_in_executor(pool, merge_multi_images, img_list, middle_interval)
                else:   # 超过 4 个，GIF
                    is_gif = True
                    gif_io = await loop.run_in_executor(pool, generate_gif, img_list, duration_time)

        config.image_list[userid_str].clear()   # 清空列表
        if is_gif:
            image_name += ".gif"
            await send_gif_file(gif_io, image_name, user_id, context)
        else:
            image_name += ".png"
            try:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=gif_io, filename=image_name)
            except error.TimedOut:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="网络超时，未能成功发送，请重新 /image")
            except:   # 由于网络不畅会引发一系列异常，光有上面那个，还不够
                await context.bot.send_message(chat_id=update.effective_chat.id, text="网络原因，未能成功发送，请重新 /image")
            else:
                pass

    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="no image left")



# 执行命令，输入 bash 中的命令 command2exec 和要传输的数据 data
def exec_command(command2exec, datafile):
    actual_command = command2exec.format(contentfile=datafile)
    subprocess.call(actual_command, shell=True)


# 推送到
async def push(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id   # 存有信息的文件
    userid_str = str(user_id)
    # 随机生成 16位 的 字母和数字
    random_str = ''.join(random.sample(string.ascii_letters + string.digits, 16))
    # 配置文件或通过命令，有设置路径则取用，没有就随机
    netstr = config.netstr if config.netstr else config.path_dict.get(str(user_id), random_str)

    # 读取保存的
    all_stored = io4message.read(userid_str) + "\n\n" + io4urlmsg.read(userid_str)
    
    if not all_stored.strip():
        # 内容为空
        await context.bot.send_message(chat_id=update.effective_chat.id, text="nothing to push")
        return
    
    if config.push_dir:
	    # 推送
        push2somewhere = config.push_dir + netstr   # 为用户分配路径
        if os.path.exists(config.push_dir):   # 若是本地目录
            io4push.append(netstr, all_stored)
            where2see = config.domain + netstr
        elif urlparse(config.push_dir).scheme in ('http', 'https'):   # 若是网址路径
            io4push.append(push2somewhere, all_stored)
            where2see = push2somewhere
        else:
            await context.bot.send_message(chat_id=config.chat_id, text="配置文件中，push_dir 填写有误")
            return
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"push done. "
                                                                            f"please visit {where2see}\n"
                                                                            f"推送完成，访问上面网址查看")
    else:
        # 都没的话，就默认发到作者的网络记事本上
        push2somewhere = config.author_webnote + netstr
        io4push.append(push2somewhere, all_stored)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"push done. "
                                                                    f"please visit {push2somewhere}\n"
                                                                    f"推送完成，访问上面网址查看")

    # 制作对话内的键盘，第一个是专门的结构，第二个函数是将这个结构转成
    inline_kb = [
        [
            InlineKeyboardButton('also clear? 清空已转存？', callback_data=str('clearall')),
            InlineKeyboardButton('dont clear! 继续保留已转存的！', callback_data=str('notclear')),
        ]
    ]
    kb_markup = InlineKeyboardMarkup(inline_kb)

    await context.bot.send_message(chat_id=update.effective_chat.id, text="and then ...", reply_markup=kb_markup)


# 只是询问，确认删除转存内容
async def sure_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inline_kb = [
        [
            InlineKeyboardButton('Confirm to clear. 确认清空', callback_data=str('clearall')),
            InlineKeyboardButton("Don't clear", callback_data=str('notclear')),
        ]
    ]
    kb_markup = InlineKeyboardMarkup(inline_kb)

    await context.bot.send_message(chat_id=update.effective_chat.id, text="Warning! this'll clear all you transfered.\n"
                                                                          "⚠️警告！这会清空转存的数据。",
                                   reply_markup=kb_markup)


# 只是询问，确认删除个人全部数据
async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inline_kb = [
        [InlineKeyboardButton('I Confirm to Delete All My Data. 我确认删除个人全部数据', callback_data='confirm_delete')],
        [InlineKeyboardButton('Cancel', callback_data='cancel_delete')]
    ]
    kb_markup = InlineKeyboardMarkup(inline_kb)

    await context.bot.send_message(chat_id=update.effective_chat.id, text="Warning! this'll Delete All Your Data.\n"
                                                                          "⚠️警告！这删除你的全部个人数据。",
                                   reply_markup=kb_markup)


# 这个才是真实操作的删除函数，clearall 指向这个，接收按键里的信息并删除转存内容 或回复不删
async def clear_or_delete_all_my_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_chat.id
    userid_str = str(user_id)
    query = update.callback_query
    await query.answer()

    if query.data == 'clearall':
        io4message.backup(userid_str)
        io4urlmsg.backup(userid_str)
        io4message.clear(userid_str)
        io4urlmsg.clear(userid_str)
        await query.edit_message_text(text=f"Selected option: {query.data}, clear done. 已清空。")
    elif query.data == 'notclear':
        await query.edit_message_text(text="OK, I haven't clear yet. 放心，还没清除。")
    # 删除数据相关的
    elif query.data == 'confirm_delete':
        io4message.del_data(userid_str)
        io4urlmsg.del_data(userid_str)
        await query.edit_message_text(text=f"All Your Data Has been Deleted.")
    elif query.data == 'cancel_delete':
        await query.edit_message_text(text="Cancel Deleting")


# 显示最早的一条信息。标准操作，只有两种情况，全空，或者开头是 '-' * 27 ，下面也只考虑这两种情况
# 顺便统计消息数量和网址数量
async def earliest_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    userid_str = str(user_id)

    stored = io4message.read(userid_str)
    stored_url = io4urlmsg.read(userid_str)

    # 如果两个都为空
    if not (stored or stored_url):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You don't have any message. "
                                                                                "你没有任何数据。")
        return

    # 统计消息数量
    msg_count = sum(line[0:27] == '-' * 27 for line in stored.split('\n'))
    url_count = len(stored_url.split('\n')) - 1
    
    first_msg = stored.split('\n', maxsplit=1)[0].strip('-')

    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text=f'The amount of messages you have saved is {msg_count}, and {url_count} urls.\n'
                                        f'Here is the earliest message you saved at {first_msg}\n'
                                        f'保存消息的数量为 {msg_count}，保存网址的数量为 {url_count}。\n'
                                        f'最早的消息是：')


# 删除最新添加的一条会返回文本，可以实现外显链接，
async def delete_last_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    userid_str = str(user_id)

    stored = io4message.read(userid_str)
    if not stored:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You don't have any message "
                                                                                "except for url."
                                                                                "你没有任何数据，可能有网址。")
        return
    
    stored_list = stored.split('\n')
    i = 0
    for line in reversed(stored_list):
        i -= 1
        if line[0:27] == '-' * 27:
            break

    last_message = '\n'.join(stored_list[i:])
    new_stored = '\n'.join(stored_list[:i])
    io4message._write(userid_str, new_stored)

    # 发送到tg
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Here is the last message you saved\n'
                                                                          f'你保存的上一条消息：')
    await context.bot.send_message(chat_id=update.effective_chat.id, text=last_message)


# 关闭机器人
async def shutdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in config.manage_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="robot will shutdown immediately")
        # 在程序停止运行时将字典保存回文件
        with open(config.json_file, 'w') as file:
            json.dump(config.path_dict, file)
        # application.stop()
        sys.exit(0)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="You are not authorized to execute this command")


# 重载配置文件
async def reload_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if user_id in config.manage_id:
        config.reload()
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="success to reload config")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="You are not authorized to execute this command")

# 未知命令回复
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.\n"
                                                                          "我不会这道题，长大了才会学习。")
