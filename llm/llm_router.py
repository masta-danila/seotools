from gpt_request import request_gpt
from deepseek_request import request_deepseek
from claude_request import request_claude
# from gemini_request import request_gemini  # Временно отключено
from grok_request import request_grok


def llm_request(model: str, messages: list) -> dict:
    """
    Принимает название модели и список сообщений.
    Вызывает соответствующую функцию запроса в зависимости от названия модели.
    """
    if model.startswith("gpt-"):
        return request_gpt(model, messages)
    elif model.startswith("deepseek-"):
        return request_deepseek(model, messages)
    elif model.startswith("claude-"):
        return request_claude(model, messages)
    # elif model.startswith("gemini-"):
    #     return request_gemini(model, messages)  # Временно отключено
    elif model.startswith("grok-"):
        return request_grok(model, messages)
    else:
        raise Exception(f"Модель {model} не поддерживается.")


if __name__ == "__main__":
    import json

    # Выполняем запрос к выбранной модели
    response = llm_request(model="grok-4-fast-reasoning",
                           messages=[
                               {"role": "user", "content": "Что такое машинное обучение? Ответь коротко."}
                           ]
                           )

    # Выводим ответ в формате JSON
    print(json.dumps(response, ensure_ascii=False, indent=2))
