import json
import os
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime, time, timezone
from llm_response_cleaner import clean_llm_content


def is_in_discount_time(discount_time_str: str) -> bool:
    """
    Проверяет, попадает ли текущий момент в UTC в интервал discount_time_str.
    Формат discount_time_str ожидается как 'UTC HH:MM-HH:MM'.
    Пример: 'UTC 16:30-00:30'.
    Возвращает True, если текущее UTC-время в заданном диапазоне.
    """
    # Сначала отбросим префикс 'UTC ' и получим '16:30-00:30'
    if not discount_time_str.startswith("UTC "):
        return False

    time_range_str = discount_time_str.split("UTC ")[1]  # '16:30-00:30'
    try:
        start_str, end_str = time_range_str.split("-")  # '16:30' и '00:30'
    except ValueError:
        return False

    start_h, start_m = map(int, start_str.split(":"))
    end_h, end_m = map(int, end_str.split(":"))

    start_time = time(hour=start_h, minute=start_m)
    end_time = time(hour=end_h, minute=end_m)

    # Текущее время UTC (исправленный вариант)
    now_utc = datetime.now(timezone.utc).time()

    if start_time < end_time:
        return start_time <= now_utc < end_time
    else:
        # Интервал переходит через полночь
        return (now_utc >= start_time) or (now_utc < end_time)


def request_deepseek(model: str, messages: list) -> dict:
    """
    Синхронная функция, делающая запрос к OpenAI.
    Возвращает словарь с очищенным контентом и рассчитанной стоимостью.
    """
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    result = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False,
        max_tokens=8000
    )
    # Извлекаем сгенерированный ответ
    answer = result.choices[0].message.content

    # Очищаем ответ (удаляем возможные обёртки ```json и т. п.)
    answer = clean_llm_content(answer)

    # Загрузка тарифов из файла llm_price.json
    pricing_path = os.path.join(os.path.dirname(__file__), "llm_pricing.json")
    with open(pricing_path, "r", encoding="utf-8") as f:
        pricing = json.load(f)

    # Извлекаем информацию о токенах из ответа API
    completion_tokens = result.usage.completion_tokens
    cached_tokens = result.usage.prompt_cache_hit_tokens
    non_cached_prompt_tokens = result.usage.prompt_cache_miss_tokens
    
    # Для reasoning моделей (deepseek-reasoner) есть отдельные reasoning tokens
    reasoning_tokens = getattr(result.usage.completion_tokens_details, 'reasoning_tokens', 0) if hasattr(result.usage, 'completion_tokens_details') else 0
    reasoning_tokens = reasoning_tokens or 0  # На случай None

    # Получаем тарифы для выбранной модели
    model_pricing = pricing.get(model)
    if not model_pricing:
        raise Exception(f"Отсутствует информация о стоимости для модели: {model}")

    input_rate = model_pricing.get("1M TOKENS INPUT (CACHE MISS)")
    cached_rate = model_pricing.get("1M TOKENS INPUT (CACHE HIT)")
    output_rate = model_pricing.get("1M TOKENS OUTPUT")

    if input_rate is None or cached_rate is None or output_rate is None:
        raise Exception(f"Не указаны тарифы для входных, кэшированных или выходных "
                        f"токенов для модели: {model}")

    # Расчёт стоимости:
    # Стоимость некэшированных prompt_tokens
    cost_non_cached_prompt = (non_cached_prompt_tokens / 1_000_000) * input_rate
    # Стоимость кэшированных prompt_tokens
    cost_cached = (cached_tokens / 1_000_000) * cached_rate
    # Стоимость output токенов (включая reasoning_tokens для reasoning моделей)
    total_output_tokens = completion_tokens + reasoning_tokens
    cost_output = (total_output_tokens / 1_000_000) * output_rate
    total_cost = cost_non_cached_prompt + cost_cached + cost_output

    # Проверяем, есть ли в тарифе поля DISCOUNT TIME и DISCOUNT
    discount_time = model_pricing.get("DISCOUNT TIME")
    discount_factor = model_pricing.get("DISCOUNT")

    if discount_time and discount_factor is not None:
        # Если текущее время попадает в указанный временной интервал,
        # умножаем итоговую стоимость на discount_factor
        if is_in_discount_time(discount_time):
            total_cost *= discount_factor

    return {"content": answer, "cost": total_cost}


if __name__ == "__main__":
    completion = request_deepseek(
        model='deepseek-chat',
        messages=[
            {"role": "user", "content": "два плюс два"}
        ]
    )

    print(completion)