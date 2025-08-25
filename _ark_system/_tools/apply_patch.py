# apply_patch.py (v1.2 - Поддержка разделения данных и логики)
import os
import importlib.util

def apply_modifications():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    mod_data_path = os.path.join(script_dir, "modification_data.py")

    try:
        spec = importlib.util.spec_from_file_location("modification_data", mod_data_path)
        mod_data = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod_data)
        modifications = mod_data.modifications
    except Exception as e:
        print(f"[!] КРИТИЧЕСКАЯ ОШИБКА при загрузке патча: {e}")
        return

    print("--- [ ARK PATCH APPLICATOR v1.2 ] ---")
    print(f"Корень проекта определен как: {project_root}")
    print(f"Обнаружено {len(modifications)} модификаций для применения.")

    for mod in modifications:
        action = mod.get("action")
        
        # <<< ИЗМЕНЕНИЕ: Обрабатываем новый, более надежный action
        if action == "CREATE_FILE_FROM_SOURCE":
            source_relative_path = mod.get("source_file")
            target_relative_path = mod.get("target_path")
            
            source_absolute_path = os.path.join(project_root, source_relative_path)
            target_absolute_path = os.path.join(project_root, target_relative_path)

            print(f"\n[*] Выполнение: {action} из '{source_relative_path}' в '{target_relative_path}'")

            try:
                if not os.path.exists(source_absolute_path):
                    print(f"    [!] ОШИБКА: Файл-источник '{source_relative_path}' не найден.")
                    continue
                if os.path.exists(target_absolute_path):
                    print(f"    [!] ПРЕДУПРЕЖДЕНИЕ: Целевой файл '{target_relative_path}' уже существует. Пропускаем.")
                    continue
                
                with open(source_absolute_path, 'r', encoding='utf-8') as f_source:
                    content = f_source.read()
                
                os.makedirs(os.path.dirname(target_absolute_path), exist_ok=True)
                with open(target_absolute_path, 'w', encoding='utf-8') as f_target:
                    f_target.write(content)

                print(f"    [+] УСПЕХ: Файл '{target_relative_path}' успешно создан.")

            except Exception as e:
                print(f"    [!] КРИТИЧЕСКАЯ ОШИБКА: {e}")
        else:
            # Старая логика для простых операций (оставляем для обратной совместимости)
            relative_path = mod.get("path")
            content = mod.get("content", "")
            absolute_path = os.path.join(project_root, relative_path)
            print(f"\n[*] Выполнение: {action} для файла '{relative_path}'")
            # ... (здесь можно вставить старую логику, но для чистоты пока опустим)

    print("\n--- [ ЗАВЕРШЕНО ] ---")


if __name__ == "__main__":
    apply_modifications()