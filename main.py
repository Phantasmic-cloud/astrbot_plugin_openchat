from astrbot.api.all import *
from astrbot.api.event import filter
from .utils import *
import time

@register(
    "openchat",
    "Phantasmic",
    "分别控制每个群的自动回复开关，魔改于SpectreCore（作者：23q3），借鉴了一点点Lunabot",
    "1.2.0",
    "https://github.com/Phantasmic-cloud/astrbot_plugin_openchat/"
)
class SpectreCore(Star):
    """
    分别控制每个群的自动回复开关，魔改于SpectreCore（作者：23q3），借鉴了一点点Lunabot
    """
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # 初始化各个工具类
        HistoryStorage.init(config)
        ImageCaptionUtils.init(context, config)

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """处理群消息喵"""
        try:
            # 保存用户消息到历史记录并尝试回复
            async for result in self._process_message(event):
                yield result
        except Exception as e:
            logger.error(f"处理群消息时发生错误: {e}")

    @event_message_type(EventMessageType.PRIVATE_MESSAGE)
    async def on_private_message(self, event: AstrMessageEvent):
        """处理私聊消息喵"""
        try:
            # 保存用户消息到历史记录并尝试回复
            async for result in self._process_message(event):
                yield result
        except Exception as e:
            logger.error(f"处理私聊消息时发生错误: {e}")
            
    async def _process_message(self, event: AstrMessageEvent):
        """处理消息的通用逻辑：保存历史记录并尝试回复"""
        # 过滤空消息(napcat会发送私聊对方正在输入的状态，导致astrbot识别为空消息)
        message_outline = event.get_message_outline()
        if not message_outline or message_outline.strip() == "":
            logger.debug("收到空消息，忽略处理")
            return

        # 保存用户消息到历史记录
        await HistoryStorage.process_and_save_user_message(event)

        # 尝试自动回复
        if ReplyDecision.should_reply(event, self.config):
            async for result in ReplyDecision.process_and_reply(event, self.config, self.context):
                yield result

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent):
        """处理bot发送的消息喵"""
        try:           
            # 保存机器人消息
            if event._result and hasattr(event._result, "chain"):
                # 检查是否为重置历史记录的提示消息，如果是则不保存
                message_text = "".join([i.text for i in event._result.chain if hasattr(i, "text")])
                if "已成功重置" in message_text and "的历史记录喵~" in message_text:
                    return
                
                await HistoryStorage.save_bot_message_from_chain(event._result.chain, event)
                logger.debug(f"已保存bot回复消息到历史记录")
                
        except Exception as e:
            logger.error(f"处理bot发送的消息时发生错误: {e}")

    from astrbot.api.provider import LLMResponse
    @filter.on_llm_response(priority=114514)
    async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse):
        """处理大模型回复喵"""
        logger.debug(f"收到大模型回复喵: {resp}")
        try:
            if resp.role != "assistant":
                return
            # 只进行文本过滤，不处理读空气逻辑
            resp.completion_text = TextFilter.process_model_text(resp.completion_text, self.config)
        except Exception as e:
            logger.error(f"处理大模型回复时发生错误: {e}")

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        """在消息发送前处理读空气功能喵"""
        try:
            result = event.get_result()
            if result is None or not result.chain:
                return

            # 检查是否为LLM结果且包含<NO_RESPONSE>标记
            if result.is_llm_result():
                # 获取消息文本内容
                message_text = ""
                for comp in result.chain:
                    if hasattr(comp, 'text'):
                        message_text += comp.text

                # 如果包含<NO_RESPONSE>标记，清空事件结果以阻止消息发送
                if "<NO_RESPONSE>" in message_text:
                    logger.debug(f"检测到读空气标记，阻止消息发送。事件结果: {event.get_result()}")
                    event.clear_result()
                    logger.debug(f"已清空事件结果: {event.get_result()}")

        except Exception as e:
            logger.error(f"处理消息发送前事件时发生错误: {e}")       

             ###autochat指令逻辑
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("autochat", alias=['聊天']) # 直接注册为顶层指令，触发方式变为 /autochat
    async def autochat(self, event: AstrMessageEvent, action: str):
        """/autochat on|off 开启或关闭本群自动回复"""
        try:
            # 检查是否为私聊
            if event.is_private_chat():
                yield event.plain_result("该指令仅支持在群聊中使用喵~")
                return
            
            # 获取当前群ID
            group_id = event.get_group_id()
            if not group_id:
                yield event.plain_result("无法获取当前群ID，操作失败喵~")
                return
            
            # 规范化群ID为字符串并去除空格
            group_id = str(group_id).strip()
            
            # 获取当前白名单列表并规范化
            enabled_groups = self.config.get("enabled_groups", [])
            enabled_groups = [str(g).strip() for g in enabled_groups]
            
            if action.lower() == "on":
                # 检查是否已在白名单中
                if group_id in enabled_groups:
                    yield event.plain_result("本群autochat已处于开启状态")
                    return
                # 添加到白名单
                enabled_groups.append(group_id)
                self.config["enabled_groups"] = enabled_groups
                self.config.save_config()
                yield event.plain_result("成功开启本群的autochat")
                
            elif action.lower() == "off":
                # 检查是否在白名单中
                if group_id not in enabled_groups:
                    yield event.plain_result("本群autochat本来就是关闭的喵~")
                    return
                # 从白名单移除
                enabled_groups.remove(group_id)
                self.config["enabled_groups"] = enabled_groups
                self.config.save_config()
                yield event.plain_result("成功关闭本群的autochat")
                
            else:
                yield event.plain_result("参数无效哦，请使用 on 或 off，示例：/autochat on 或 /autochat off")
                
        except Exception as e:
            logger.error(f"处理autochat指令时发生错误: {e}")
            yield event.plain_result(f"操作失败喵：{str(e)}")

    # 将原版 history, reset, mute, unmute, callllm 函数删除
