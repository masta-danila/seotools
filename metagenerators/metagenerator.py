"""
Метагенератор - модуль для генерации SEO-текстов (H1, Title, Description) через LLM.
"""
import sys
import os
import json
import asyncio
from typing import List, Dict
from pathlib import Path

# Добавляем путь к папке llm для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'llm'))

from llm_router import llm_request  # type: ignore


async def generate_seo_texts(
    title_words: List[str],
    description_words: List[str],
    company_name: str,
    main_query: str = None,
    h1_variables: List[str] = None,
    title_variables: List[str] = None,
    description_variables: List[str] = None,
    model: str = "claude-sonnet-4-5-20250929"
) -> Dict[str, str]:
    """
    Генерирует H1, Title и Description через LLM
    
    Args:
        title_words: Список слов для использования в title
        description_words: Список слов для использования в description
        company_name: Название компании
        main_query: Основной поисковый запрос (если None, берется первое слово из title_words)
        h1_variables: Список переменных Битрикса для h1 (например, ["#PRICE#", "#NAME#"])
        title_variables: Список переменных Битрикса для title (например, ["#PRICE#", "#NAME#"])
        description_variables: Список переменных Битрикса для description
        model: Модель LLM для генерации
    
    Returns:
        Словарь с ключами: h1, title, description, cost
    """
    # Определяем основной запрос
    if main_query is None:
        main_query = title_words[0] if title_words else ""
    
    # Формируем промпт с условной логикой
    prompt_parts = [
        f"- основной запрос: {main_query}",
        "- основной запрос используем ближе к началу в h1, title, description",
        "- h1 должен быть кратким и емким (2-5 слов)",
        "- в h1 название компании использовать не нужно",
        "- в h1 и title нельзя дублировать слова (каждое слово используется только один раз)",
    ]
    
    # Добавляем переменные для h1 только если они есть
    if h1_variables and len(h1_variables) > 0:
        prompt_parts.append(
            f"- в h1 используй переменные Битрикса: {', '.join(h1_variables)} (вставь их естественным образом в текст)"
        )
    
    prompt_parts.append(f"- в title используем слова: {', '.join(title_words)}")
    prompt_parts.append("- title должен быть коммерчески привлекательным и побуждать к действию")
    prompt_parts.append("- старайся обходиться без : и - в title")
    
    # Добавляем переменные для title только если они есть
    if title_variables and len(title_variables) > 0:
        prompt_parts.append(
            f"- в title используй переменные Битрикса: {', '.join(title_variables)} (вставь их естественным образом в текст)"
        )
    
    prompt_parts.append(f"- в description используем слова: {', '.join(description_words)}")
    
    # Добавляем переменные для description только если они есть
    if description_variables and len(description_variables) > 0:
        prompt_parts.append(
            f"- в description используй переменные Битрикса: {', '.join(description_variables)} (вставь их естественным образом в текст)"
        )
    
    prompt_parts.append(f"- используй в h1, title и description название компании: «{company_name}»")
    prompt_parts.append("- ты можешь менять падежи и склонения слов для более естественного текста")
    
    # Собираем финальный промпт
    prompt = "Напиши h1, title и description по следующим требованиям:\n" + "\n".join(prompt_parts)
    prompt += """

Верни результат СТРОГО в формате JSON (без дополнительного текста):
{
  "h1": "текст h1",
  "title": "текст title",
  "description": "текст description"
}"""
    
    # Запускаем синхронный llm_request в executor
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: llm_request(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
    )
    
    # Парсим ответ
    content = response.get("content", "{}")
    
    try:
        result = json.loads(content)
        return {
            "h1": result.get("h1", ""),
            "title": result.get("title", ""),
            "description": result.get("description", ""),
            "cost": response.get("cost", 0)
        }
    except json.JSONDecodeError:
        # Если не удалось распарсить JSON, возвращаем пустой результат
        return {
            "h1": "",
            "title": "",
            "description": "",
            "cost": response.get("cost", 0),
            "error": "Failed to parse LLM response",
            "raw_content": content
        }


def save_results_to_json(results: Dict, filename: str = "jsontests/seo_texts_results.json", silent: bool = False) -> None:
    """
    Сохраняет результаты генерации в JSON файл
    
    Args:
        results: Словарь с результатами
        filename: Путь к файлу для сохранения
        silent: Не выводить сообщение о сохранении
    """
    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    if not silent:
        print(f"\n✓ Результаты генерации сохранены в файл: {filename}")
        print(f"  Для проверки и выбора лучшего варианта запустите: arsenkin/metatag_checker.py")


if __name__ == "__main__":
    """
    Тест генерации SEO-текстов - выбирает случайный URL из lemmatizer_processor_results.json
    и генерирует H1, Title, Description через LLM
    """
    import random
    
    async def test():
        try:
            # Определяем пути относительно корня проекта
            project_root = Path(__file__).parent.parent
            input_file = project_root / "jsontests" / "step4_lemmatized.json"
            output_file = project_root / "jsontests" / "metagenerator_test_results.json"
            
            # Загружаем данные из lemmatizer_processor_results.json
            with open(input_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Собираем все URL из всех spreadsheet
            all_urls = []
            for spreadsheet_id, spreadsheet_info in data.items():
                urls_dict = spreadsheet_info.get('urls', {})
                for url in urls_dict.keys():
                    all_urls.append((spreadsheet_id, url))
            
            if not all_urls:
                print("В данных не найдено ни одного URL")
                return
            
            # Выбираем случайный URL
            spreadsheet_id, target_url = random.choice(all_urls)
            url_data = data[spreadsheet_id]['urls'][target_url]
            
            # Извлекаем данные
            title_words = url_data.get("lemmatized_title_words", [])
            description_words = url_data.get("lemmatized_description_words", [])
            company_name = url_data.get("company_name", "Ворота нам")
            queries = url_data.get("queries", [])
            main_query = queries[0] if queries else "ворота"
            
            # Переменные Битрикса
            h1_variables = url_data.get("variables_h1", [])
            title_variables = url_data.get("variables_title", [])
            description_variables = url_data.get("variables_description", [])
            
            print(f"\nВыбран случайный URL: {target_url}")
            print(f"\nПараметры генерации:")
            print(f"  Основной запрос: {main_query}")
            print(f"  Компания: {company_name}")
            print(f"  Title words: {title_words}")
            print(f"  Description words: {description_words}")
            print(f"  H1 variables: {h1_variables}")
            print(f"  Title variables: {title_variables}")
            print(f"  Description variables: {description_variables}")
            print("\nОтправка запроса в LLM...")
            
            # Генерируем SEO-тексты
            seo_texts = await generate_seo_texts(
                title_words=title_words,
                description_words=description_words,
                company_name=company_name,
                main_query=main_query,
                h1_variables=h1_variables,
                title_variables=title_variables,
                description_variables=description_variables,
                model="claude-sonnet-4-5-20250929"
            )
            
            # Добавляем метаданные
            seo_texts["metadata"] = {
                "url": target_url,
                "title_words": title_words,
                "description_words": description_words,
                "company_name": company_name,
                "main_query": main_query,
                "h1_variables": h1_variables,
                "title_variables": title_variables,
                "description_variables": description_variables
            }
            
            # Сохраняем результат
            save_results_to_json(seo_texts, str(output_file), silent=False)
            
            # Выводим результаты
            print("\n" + "="*80)
            print("РЕЗУЛЬТАТЫ:")
            print("="*80)
            print(f"\nH1: {seo_texts.get('h1', '')}")
            print(f"\nTitle: {seo_texts.get('title', '')}")
            print(f"\nDescription: {seo_texts.get('description', '')}")
            print(f"\nСтоимость: ${seo_texts.get('cost', 0):.6f}")
            
            if "error" in seo_texts:
                print(f"\nОшибка: {seo_texts['error']}")
                if "raw_content" in seo_texts:
                    print(f"\nСырой ответ LLM:\n{seo_texts['raw_content']}")
            
        except FileNotFoundError as e:
            print(f"Файл не найден: {e}")
        except Exception as e:
            print(f"Ошибка: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(test())
