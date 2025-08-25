# apply_patch.py (v4.1 - Исправлена ошибка создания файлов в корне)
import os
import sys
import base64
import subprocess
import importlib.util

# ... (остальной код остается тем же, меняется только одна функция)

def apply_modifications():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    mod_data_path = os.path.join(script_dir, "modification_data.py")
    
    print("--- [ ARK UNIVERSAL PATCH APPLICATOR v4.1 ] ---")
    
    # --- 1. Загрузка патча ---
    try:
        spec = importlib.util.spec_from_file_location("modification_data", mod_data_path)
        mod_data = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod_data)
        modifications = mod_data.modifications
        commit_message = getattr(mod_data, "commit_message", "")
    except Exception as e:
        print(f"[!] КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить 'modification_data.py'.\n    {e}")
        return

    # --- 2. Применение изменений к файлам ---
    os.chdir(project_root)
    for mod in modifications:
        action = mod.get("action")
        path = mod.get("path")
        print(f"\n[*] Применяю: {action} для '{path}'")
        try:
            content = mod.get("content", "")

            # <<< ИСПРАВЛЕНИЕ ЗДЕСЬ >>>
            # Создаем директорию, только если она указана в пути
            dirname = os.path.dirname(path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            # <<< КОНЕЦ ИСПРАВЛЕНИЯ >>>

            if action == "CREATE_OR_REPLACE_FILE":
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print("    [+] УСПЕХ: Файл создан/перезаписан.")
            
        except Exception as e:
            print(f"    [!] ОШИБКА ФАЙЛА: {e}")
            return

    # ... (остальная часть с Git-командами остается без изменений)
    # --- 3. Синхронизация с Git (если есть сообщение коммита) ---
    if commit_message:
        # ... (код для Git)
        pass # Этот блок не меняется
    
    print("\n--- [ ЗАВЕРШЕНО ] ---")

# Полный код для копирования
def run_git_command(command, commit_message=""):
    final_command = command.replace("{commit_message}", commit_message)
    try:
        process = subprocess.Popen(final_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        for line in process.stdout:
            print(line, end='')
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, final_command)
        return True
    except subprocess.CalledProcessError: return False
    except Exception as e:
        print(f"[!] Непредвиденная ошибка GIT: {e}")
        return False

def apply_modifications():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    mod_data_path = os.path.join(script_dir, "modification_data.py")
    
    print("--- [ ARK UNIVERSAL PATCH APPLICATOR v4.1 ] ---")
    print(f"Корень проекта: {project_root}")

    try:
        spec = importlib.util.spec_from_file_location("modification_data", mod_data_path)
        mod_data = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod_data)
        modifications = mod_data.modifications
        commit_message = getattr(mod_data, "commit_message", "")
    except Exception as e:
        print(f"[!] КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить 'modification_data.py'.\n    {e}")
        return

    os.chdir(project_root)
    for mod in modifications:
        action = mod.get("action")
        path = mod.get("path")
        print(f"\n[*] Применяю: {action} для '{path}'")
        try:
            content = mod.get("content", "")
            
            dirname = os.path.dirname(path)
            if dirname: # Создаем директорию, только если она не пустая
                os.makedirs(dirname, exist_ok=True)

            if action == "CREATE_OR_REPLACE_FILE":
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print("    [+] УСПЕХ: Файл создан/перезаписан.")

        except Exception as e:
            print(f"    [!] ОШИБКА ФАЙЛА: {e}")
            return

    if commit_message:
        print("\n--- [ АВТОМАТИЧЕСКАЯ СИНХРОНИЗАЦИЯ ] ---")
        if not run_git_command("git add ."): return
        if not run_git_command('git commit -m "{commit_message}"', commit_message): return
        if not run_git_command("git push origin main"):
             print("\n[!] ПРЕДУПРЕЖДЕНИЕ: Не удалось отправить на GitHub. Изменения закоммичены локально.")
        else:
            print("\n[+] Синхронизация с GitHub завершена.")
    else:
        print("\n[i] Сообщение коммита не указано. Автоматическая синхронизация пропущена.")

    try:
        os.remove(mod_data_path)
        print("\n[*] Самоочистка: 'modification_data.py' удален.")
    except Exception as e:
        print(f"\n[!] ОШИБКА ОЧИСТКИ: {e}")
    
    print("\n--- [ ЗАВЕРШЕНО ] ---")


if __name__ == "__main__":
    apply_modifications()