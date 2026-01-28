import json
import os
import anthropic
from dotenv import load_dotenv
from llm_response_cleaner import clean_llm_content


def request_claude(model: str, messages: list[dict]) -> dict:
    """
    Синхронная функция, делающая запрос к Anthropic.
    """
    load_dotenv()
    client = anthropic.Anthropic()
    result = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=messages
    )
    # Извлекаем сгенерированный ответ
    answer = result.content[0].text

    # Очищаем ответ (удаляем возможные обёртки ```json и т. п.)
    answer = clean_llm_content(answer)

    # Загрузка тарифов из файла llm_price.json
    pricing_path = os.path.join(os.path.dirname(__file__), "llm_pricing.json")
    with open(pricing_path, "r", encoding="utf-8") as f:
        pricing = json.load(f)

    # Извлекаем информацию о токенах из ответа API
    input_tokens = result.usage.input_tokens
    output_tokens = result.usage.output_tokens

    # Получаем тарифы для выбранной модели
    model_pricing = pricing.get(model)
    if not model_pricing:
        raise Exception(f"Отсутствует информация о стоимости для модели: {model}")

    input_rate = model_pricing.get("input_tokens")
    output_rate = model_pricing.get("output_tokens")

    if input_rate is None or output_rate is None:
        raise Exception(f"Не указаны тарифы для входных, кэшированных или выходных токенов для модели: {model}")

    # Расчет стоимости:
    # Стоимость некэшированных prompt_tokens
    cost_input = (input_tokens / 1_000_000) * input_rate
    # Стоимость output токенов
    cost_output = (output_tokens / 1_000_000) * output_rate
    total_cost = cost_input + cost_output

    return {"content": answer, "cost": total_cost}


if __name__ == "__main__":
    completion = request_claude(
        model='claude-sonnet-4-5-20250929',
        messages=[
            {"role": "assistant", "content": "Привет! Чем я могу вам помочь сегодня?"},
            {"role": "user", "content": "Сколько будет два плюс два?"}
        ]
    )

    print(completion)