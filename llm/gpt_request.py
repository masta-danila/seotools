import json
import os
from openai import OpenAI
from dotenv import load_dotenv
from llm_response_cleaner import clean_llm_content


def request_gpt(model: str, messages: list) -> dict:
    """
    Синхронная функция, делающая запрос к OpenAI.
    Возвращает словарь с очищенным контентом и рассчитанной стоимостью.
    """
    load_dotenv()
    client = OpenAI()
    result = client.chat.completions.create(
        model=model,
        messages=messages
    )

    # Выводим первичный сырой ответ от OpenAI API в красивом формате
    # print("=== ПЕРВИЧНЫЙ СЫРОЙ ОТВЕТ ОТ OPENAI API ===")
    # print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False, default=str))
    # print("=== КОНЕЦ ПЕРВИЧНОГО ОТВЕТА ===")

    # Извлекаем сгенерированный ответ
    answer = result.choices[0].message.content

    # Очищаем ответ (удаляем возможные обёртки ```json и т. п.)
    answer = clean_llm_content(answer)

    # Загрузка тарифов из файла llm_price.json
    pricing_path = os.path.join(os.path.dirname(__file__), "llm_pricing.json")
    with open(pricing_path, "r", encoding="utf-8") as f:
        pricing = json.load(f)

    # Извлекаем информацию о токенах из ответа API
    prompt_tokens = result.usage.prompt_tokens
    completion_tokens = result.usage.completion_tokens
    cached_tokens = result.usage.prompt_tokens_details.cached_tokens
    
    # Для reasoning моделей (o1, o3) есть отдельные reasoning tokens
    reasoning_tokens = getattr(result.usage.completion_tokens_details, 'reasoning_tokens', 0) if hasattr(result.usage, 'completion_tokens_details') else 0
    reasoning_tokens = reasoning_tokens or 0  # На случай None

    # Рассчитываем количество некэшированных prompt_tokens
    non_cached_prompt_tokens = prompt_tokens - cached_tokens

    # Получаем тарифы для выбранной модели
    model_pricing = pricing.get(model)
    if not model_pricing:
        raise Exception(f"Отсутствует информация о стоимости для модели: {model}")

    input_rate = model_pricing.get("1M input tokens")
    cached_rate = model_pricing.get("1M cached** input tokens")
    output_rate = model_pricing.get("1M output tokens")

    if input_rate is None or cached_rate is None or output_rate is None:
        raise Exception(f"Не указаны тарифы для входных, кэшированных или выходных "
                        f"токенов для модели: {model}")

    # Расчёт стоимости:
    # Стоимость некэшированных prompt_tokens
    cost_non_cached_prompt = (non_cached_prompt_tokens / 1_000_000) * input_rate
    # Стоимость кэшированных prompt_tokens
    cost_cached = (cached_tokens / 1_000_000) * cached_rate
    # Стоимость output токенов (включая reasoning_tokens для o1/o3 моделей)
    total_output_tokens = completion_tokens + reasoning_tokens
    cost_output = (total_output_tokens / 1_000_000) * output_rate
    total_cost = cost_non_cached_prompt + cost_cached + cost_output

    return {"content": answer, "cost": total_cost}


if __name__ == "__main__":
    completion = request_gpt(
        model='gpt-5.2',
        messages=[
            {"role": "user", "content": "Флорист просто чудо, собрала невероятный букет из роз и гербер, все в моих любимых оттенках. Привезли без опозданий (заказ онлайн оформляла), упаковка стильная, не мятая. Жена в восторге была, спасибо вам от души."}
        ]
    )

    print(completion)