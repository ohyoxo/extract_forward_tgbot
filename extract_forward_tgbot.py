"""
0.15
添加根据频道只抽取url
自动根据系统切换一些参数，无需部署时手动
保存时询问是否清除，修复bug：A姐发的是纯文本
0.16  单用户以奇数
增加requirements.txt，无限个backup，两个保存文件分别显示数量
0.17   删除最新添加的一条会返回文本，可以实现外显链接，

0.21 多用户版本以偶数开始
保存的时候，后面加自定义的网址链接
24小时内会是占用时间，别人不可以再用  单独一个命令设置网址
"""

import sys
import json

from telegram import Update
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

import config   # print(config.ENVIRONMENT)  # 打印ENVIRONMENT的值
from tgbotBehavior import start, transfer, clear, push, unknown, earliest_msg, sure_clear, delete_last_msg
from multi import set_config


# 关闭机器人，这个只能在这，因为 updater 和 sys
async def shutdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) in config.manage_id:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="robot will shutdown immediately")
        # 在程序停止运行时将字典保存回文件
        with open(config.json_file, 'w') as file:
            json.dump(config.path_dict, file)
        # application.stop()
        sys.exit(0)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="You are not authorized to execute this command")


if __name__ == '__main__':
    application = ApplicationBuilder().token(config.bot_token).build()

    # 类似路由，接收到 /start 执行哪个函数，
    start_handler = CommandHandler('start', start)
    # 转存
    transfer_handler = MessageHandler((~filters.COMMAND), transfer)
    # # 转存含图片的
    # transfer_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), transfer)
    # 确认删除转存内容
    sure_clear_handler = CommandHandler('clear', sure_clear)
    # 推送到
    push_handler = CommandHandler('push', push)
    # 显示最早的一条信息
    earliest_msg_handler = CommandHandler('emsg', earliest_msg)
    # 删除最新的一条信息
    delete_msg_handler = CommandHandler('dmsg', delete_last_msg)
    # 设置参数，如网址路径
    set_config_handler = CommandHandler('set', set_config)
    # 停止机器人
    shutdown_handler = CommandHandler('shutdown', shutdown)

    # 注册 start_handler ，以便调度
    application.add_handler(start_handler)
    application.add_handler(transfer_handler)
    application.add_handler(sure_clear_handler)
    # 删除转存内容 或回复不删
    application.add_handler(CallbackQueryHandler(clear))

    application.add_handler(push_handler)
    application.add_handler(earliest_msg_handler)
    application.add_handler(delete_msg_handler)
    application.add_handler(set_config_handler)
    application.add_handler(shutdown_handler)

    # 未知命令回复。必须放到最后，会先判断前面的命令，都不是才会执行这个
    unknown_handler = MessageHandler(filters.COMMAND, unknown)
    application.add_handler(unknown_handler)

    # 启动
    application.run_polling()

    # 在程序停止运行时将字典保存回文件
    with open(config.json_file, 'w') as file:
        json.dump(config.path_dict, file)

