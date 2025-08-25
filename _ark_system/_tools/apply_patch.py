# apply_patch.py (v1.1 - Усиленная версия с определением корня проекта)
import os
import importlib.util

def apply_modifications():
    """
    Applies a series of file modifications defined in modification_data.py.
    """
    # <<< ИЗМЕНЕНИЕ: Определяем корень проекта (предполагаем, что _tools находится на 2 уровня ниже)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    
    # Путь к файлу с данными патча
    mod_data_path = os.path.join(script_dir, "modification_data.py")

    try:
        spec = importlib.util.spec_from_file_location("modification_data", mod_data_path)
        mod_data = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod_data)
        modifications = mod_data.modifications
    except FileNotFoundError:
        print(f"[!] ОШИБКА: Файл 'modification_data.py' не найден по пути '{mod_data_path}'.")
        return
    except Exception as e:
        print(f"[!] КРИТИЧЕСКАЯ ОШИБКА при загрузке патча: {e}")
        return

    print("--- [ ARK PATCH APPLICATOR v1.1 ] ---")
    print(f"Корень проекта определен как: {project_root}")
    print(f"Обнаружено {len(modifications)} модификаций для применения.")

    for mod in modifications:
        action = mod.get("action")
        relative_path = mod.get("path")
        content = mod.get("content", "")
        
        # <<< ИЗМЕНЕНИЕ: Строим абсолютный путь от корня проекта
        absolute_path = os.path.join(project_root, relative_path)

        print(f"\n[*] Выполнение: {action} для файла '{relative_path}'")

        try:
            if action == "CREATE_FILE":
                if os.path.exists(absolute_path):
                    print(f"    [!] ПРЕДУПРЕЖДЕНИЕ: Файл '{relative_path}' уже существует. Пропускаем создание.")
                    continue
                os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
                with open(absolute_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"    [+] УСПЕХ: Файл '{relative_path}' создан.")

            elif action == "APPEND_TEXT":
                if not os.path.exists(absolute_path):
                    print(f"    [!] ОШИБКА: Файл '{relative_path}' для добавления текста не найден.")
                    continue
                with open(absolute_path, 'a', encoding='utf-8') as f:
                    f.write(content)
                print(f"    [+] УСПЕХ: Текст добавлен в '{relative_path}'.")
            
            else:
                print(f"    [!] НЕИЗВЕСТНОЕ ДЕЙСТВИЕ: '{action}'. Пропускаем.")

        except Exception as e:
            print(f"    [!] КРИТИЧЕСКАЯ ОШИБКА при выполнении действия: {e}")
    
    print("\n--- [ ЗАВЕРШЕНО ] ---")


if __name__ == "__main__":
    apply_modifications()