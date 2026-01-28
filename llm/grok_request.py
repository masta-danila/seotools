import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from llm_response_cleaner import clean_llm_content


def request_grok(model: str, messages: list) -> dict:
    """
    Синхронная функция, делающая запрос к X.AI Grok.
    Возвращает словарь с очищенным контентом и рассчитанной стоимостью.
    
    ВАЖНО: reasoning_tokens считаются ОТДЕЛЬНО от completion_tokens.
    Для моделей с reasoning общий output = completion_tokens + reasoning_tokens.
    Оба типа токенов стоят одинаково (по тарифу output tokens).
    """
    load_dotenv()
    XAI_API_KEY = os.getenv("XAI_API_KEY")
    
    # Инициализация клиента X.AI
    client = OpenAI(
        api_key=XAI_API_KEY,
        base_url="https://api.x.ai/v1",
    )
    
    result = client.chat.completions.create(
        model=model,
        messages=messages
    )

    # Выводим первичный сырой ответ от Grok API в красивом формате
    # print("=== ПЕРВИЧНЫЙ СЫРОЙ ОТВЕТ ОТ GROK API ===")
    # print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False, default=str))
    # print("=== КОНЕЦ ПЕРВИЧНОГО ОТВЕТА ===")

    # Извлекаем сгенерированный ответ
    answer = result.choices[0].message.content

    # Очищаем ответ (удаляем возможные обёртки ```json и т. п.)
    answer = clean_llm_content(answer)

    # Загрузка тарифов из файла llm_pricing.json
    pricing_path = os.path.join(os.path.dirname(__file__), "llm_pricing.json")
    with open(pricing_path, "r", encoding="utf-8") as f:
        pricing = json.load(f)

    # Извлекаем информацию о токенах из ответа API
    prompt_tokens = result.usage.prompt_tokens
    completion_tokens = result.usage.completion_tokens
    
    # Извлекаем детали токенов
    cached_tokens = getattr(result.usage.prompt_tokens_details, 'cached_tokens', 0) or 0
    reasoning_tokens = getattr(result.usage.completion_tokens_details, 'reasoning_tokens', 0) or 0

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
    
    # Стоимость output токенов
    # ВАЖНО: completion_tokens НЕ включает reasoning_tokens, они отдельно!
    # Поэтому нужно считать оба типа токенов
    total_output_tokens = completion_tokens + reasoning_tokens
    cost_completion = (total_output_tokens / 1_000_000) * output_rate

    # Общая стоимость запроса
    total_cost = cost_non_cached_prompt + cost_cached + cost_completion

    return {
        "content": answer,
        "cost": total_cost
    }


if __name__ == "__main__":
    # Тест функции
    model = "grok-4-0709"
    messages = [
        {
            "role": "user",
            "content": "Объясни простыми словами, что такое квантовая запутанность."
        }
    ]
    
    result = request_grok(model, messages)
    
    print("="*60)
    print("ОТВЕТ:")
    print("="*60)
    print(result["content"])
    print("\n" + "="*60)
    print(f"СТОИМОСТЬ: ${result['cost']:.6f}")
    print("="*60)

