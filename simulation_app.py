#!/usr/bin/env python3
"""
Interactive application for control function simulation.
Features:
- Two vertical blocks: settings and data input
- Hierarchical structure: Control Function Blocks -> Control Functions -> Arguments
- XML save/load functionality
- Simulation execution with formula evaluation
- Data file loading for time-dependent arguments
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os
import re
import math
from datetime import datetime
from typing import Dict, List, Optional, Any


class Argument:
    """Represents a 3rd level argument in the hierarchy."""
    
    def __init__(self, short_name: str = "", long_name: str = "", 
                 module: str = "", ref_type: str = "object",
                 data_file: str = ""):
        self.short_name = short_name
        self.long_name = long_name
        self.module = module
        self.ref_type = ref_type  # "object", "t", "dt"
        self.data_file = data_file
        self.data_values: Dict[float, float] = {}  # time -> value
        
    def load_data_file(self, filepath: str) -> bool:
        """Load time-dependent data from a text file (2 columns: time, value)."""
        if not filepath or not os.path.exists(filepath):
            return False
        
        try:
            self.data_values = {}
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        time_val = float(parts[0])
                        value = float(parts[1])
                        self.data_values[time_val] = value
            self.data_file = filepath
            return True
        except Exception as e:
            print(f"Error loading data file: {e}")
            return False
    
    def get_value_at_time(self, t: float) -> Optional[float]:
        """Get interpolated value at given time from loaded data."""
        if not self.data_values:
            return None
        
        times = sorted(self.data_values.keys())
        if t <= times[0]:
            return self.data_values[times[0]]
        if t >= times[-1]:
            return self.data_values[times[-1]]
        
        # Linear interpolation
        for i in range(len(times) - 1):
            if times[i] <= t <= times[i + 1]:
                t1, t2 = times[i], times[i + 1]
                v1, v2 = self.data_values[t1], self.data_values[t2]
                return v1 + (v2 - v1) * (t - t1) / (t2 - t1)
        
        return None
    
    def to_xml(self) -> ET.Element:
        """Convert to XML element."""
        elem = ET.Element("Arg")
        elem.set("ShortName", self.short_name)
        elem.set("LongName", self.long_name)
        if self.module:
            elem.set("Module", self.module)
        return elem
    
    @classmethod
    def from_xml(cls, elem: ET.Element) -> 'Argument':
        """Create from XML element."""
        arg = cls()
        arg.short_name = elem.get("ShortName", "")
        arg.long_name = elem.get("LongName", "")
        arg.module = elem.get("Module", "")
        return arg


class ControlFunction:
    """Represents a 2nd level control function."""
    
    def __init__(self, name: str = "", initial_value: float = 0.0,
                 formula: str = "", output_file: str = ""):
        self.name = name
        self.initial_value = initial_value
        self.formula = formula
        self.output_file = output_file
        self.arguments: List[Argument] = []
        self.current_value = initial_value
        
    def add_argument(self, arg: Argument):
        self.arguments.append(arg)
    
    def evaluate(self, t: float, dt: float, func_registry: Dict[str, 'ControlFunction'], 
                 constants: Optional[Dict[str, float]] = None) -> float:
        """Evaluate the formula at given time."""
        if not self.formula:
            return self.initial_value
        
        # Build context for evaluation
        context = {
            't': t,
            'dt': dt,
            'math': math,
        }
        
        # Add constants to context
        if constants:
            for name, value in constants.items():
                context[name] = value
        
        # Add arguments to context
        for arg in self.arguments:
            if arg.ref_type == "t":
                context[arg.short_name] = t
            elif arg.ref_type == "dt":
                context[arg.short_name] = dt
            elif arg.data_values:
                val = arg.get_value_at_time(t)
                if val is not None:
                    context[arg.short_name] = val
            else:
                # Try to resolve reference to another control function
                if "ControlFunc" in arg.long_name:
                    match = re.search(r'ControlFunc\(([^)]+)\)', arg.long_name)
                    if match:
                        ref_name = match.group(1)
                        if ref_name in func_registry:
                            context[arg.short_name] = func_registry[ref_name].current_value
                else:
                    # Use initial value or 0
                    context[arg.short_name] = 0.0
        
        try:
            # Replace logical operators for Python evaluation
            expr = self.formula
            expr = expr.replace(' and ', ' and ')
            expr = expr.replace(' or ', ' or ')
            expr = expr.replace(' not ', ' not ')
            
            # Handle ternary operator (? :)
            # Simple pattern: (condition) ? true_val : false_val
            ternary_pattern = r'\(([^?]+)\)\s*\?\s*([^:]+)\s*:\s*([^)]+)'
            
            def replace_ternary(match):
                condition = match.group(1).strip()
                true_val = match.group(2).strip()
                false_val = match.group(3).strip()
                return f"({true_val}) if ({condition}) else ({false_val})"
            
            while '?' in expr and ':' in expr:
                new_expr = re.sub(ternary_pattern, replace_ternary, expr)
                if new_expr == expr:
                    break
                expr = new_expr
            
            result = eval(expr, {"__builtins__": {}}, context)
            self.current_value = float(result)
            return self.current_value
        except Exception as e:
            print(f"Error evaluating formula for {self.name}: {e}")
            return self.initial_value
    
    def to_xml(self) -> ET.Element:
        """Convert to XML element."""
        elem = ET.Element("ControlFunc")
        elem.set("Name", self.name)
        elem.set("Func", str(self.initial_value))
        elem.set("Formula", self.formula)
        elem.set("OutFile", self.output_file)
        
        for arg in self.arguments:
            elem.append(arg.to_xml())
        
        return elem
    
    @classmethod
    def from_xml(cls, elem: ET.Element) -> 'ControlFunction':
        """Create from XML element."""
        func = cls()
        func.name = elem.get("Name", "")
        func.initial_value = float(elem.get("Func", "0.0"))
        func.formula = elem.get("Formula", "")
        func.output_file = elem.get("OutFile", "")
        
        for arg_elem in elem.findall("Arg"):
            func.arguments.append(Argument.from_xml(arg_elem))
        
        return func


class ControlFunctionBlock:
    """Represents a 1st level block of control functions."""
    
    def __init__(self, name: str = ""):
        self.name = name
        self.control_functions: List[ControlFunction] = []
    
    def add_control_function(self, func: ControlFunction):
        self.control_functions.append(func)
    
    def to_xml(self) -> ET.Element:
        """Convert block and all contents to XML."""
        root = ET.Element("ControlFuncBlock")
        root.set("Name", self.name)
        
        for func in self.control_functions:
            root.append(func.to_xml())
        
        return root
    
    @classmethod
    def from_xml(cls, elem: ET.Element) -> 'ControlFunctionBlock':
        """Create from XML element."""
        block = cls()
        block.name = elem.get("Name", "")
        
        for func_elem in elem.findall("ControlFunc"):
            block.control_functions.append(ControlFunction.from_xml(func_elem))
        
        return block


class SimulationApp:
    """Main application class."""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Control Function Simulation")
        self.root.geometry("1200x800")
        
        # Data storage
        self.blocks: List[ControlFunctionBlock] = []
        self.func_registry: Dict[str, ControlFunction] = {}
        
        # Simulation parameters
        self.start_time = tk.StringVar(value="0.0")
        self.end_time = tk.StringVar(value="10.0")
        self.time_step = tk.StringVar(value="0.1")
        self.work_directory = tk.StringVar(value="")
        
        # Constants storage
        self.constants: Dict[str, float] = {}
        
        # Setup UI
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the main user interface."""
        # Main horizontal paned window
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left panel - Settings
        left_frame = ttk.LabelFrame(main_paned, text="Simulation Settings")
        main_paned.add(left_frame, weight=1)
        
        self.setup_settings_panel(left_frame)
        
        # Right panel - Data Input
        right_frame = ttk.LabelFrame(main_paned, text="Control Functions Configuration")
        main_paned.add(right_frame, weight=3)
        
        self.setup_data_input_panel(right_frame)
    
    def setup_settings_panel(self, parent: ttk.LabelFrame):
        """Setup the left settings panel."""
        # Time settings frame
        time_frame = ttk.LabelFrame(parent, text="Time Parameters")
        time_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Start time
        ttk.Label(time_frame, text="Start Time:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.start_entry = ttk.Entry(time_frame, textvariable=self.start_time, width=20)
        self.start_entry.grid(row=0, column=1, padx=5, pady=5)
        
        # End time
        ttk.Label(time_frame, text="End Time:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.end_entry = ttk.Entry(time_frame, textvariable=self.end_time, width=20)
        self.end_entry.grid(row=1, column=1, padx=5, pady=5)
        
        # Time step
        ttk.Label(time_frame, text="Time Step (dt):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.step_entry = ttk.Entry(time_frame, textvariable=self.time_step, width=20)
        self.step_entry.grid(row=2, column=1, padx=5, pady=5)
        
        # Work directory frame
        dir_frame = ttk.LabelFrame(parent, text="Work Directory")
        dir_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(dir_frame, text="Directory:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.work_directory, width=30)
        self.dir_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(dir_frame, text="Browse", command=self.browse_work_directory).grid(row=0, column=2, padx=5, pady=5)
        
        # Constants frame
        const_frame = ttk.LabelFrame(parent, text="Constants")
        const_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Constants listbox with scrollbar
        const_list_frame = ttk.Frame(const_frame)
        const_list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        const_scroll = ttk.Scrollbar(const_list_frame)
        const_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.constants_listbox = tk.Listbox(const_list_frame, yscrollcommand=const_scroll.set)
        self.constants_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        const_scroll.config(command=self.constants_listbox.yview)
        
        # Constants buttons
        const_btn_frame = ttk.Frame(const_frame)
        const_btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(const_btn_frame, text="Add Constant", command=self.add_constant).pack(side=tk.LEFT, padx=2)
        ttk.Button(const_btn_frame, text="Edit Constant", command=self.edit_constant).pack(side=tk.LEFT, padx=2)
        ttk.Button(const_btn_frame, text="Delete Constant", command=self.delete_constant).pack(side=tk.LEFT, padx=2)
        
        # Buttons frame
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Save to XML button
        save_btn = ttk.Button(btn_frame, text="Save to XML", command=self.save_to_xml)
        save_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Load from XML button
        load_btn = ttk.Button(btn_frame, text="Load from XML", command=self.load_from_xml)
        load_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Run simulation button
        run_btn = ttk.Button(btn_frame, text="Run Simulation", command=self.run_simulation)
        run_btn.pack(side=tk.RIGHT, padx=5, pady=5)
        
        # Status label
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(parent, textvariable=self.status_var, relief=tk.SUNKEN)
        status_label.pack(fill=tk.X, padx=10, pady=5)
    
    def browse_work_directory(self):
        """Browse for work directory."""
        directory = filedialog.askdirectory(title="Select Work Directory")
        if directory:
            self.work_directory.set(directory)
    
    def add_constant(self):
        """Add a new constant."""
        dialog = ConstantDialog(self.root, "Add Constant")
        if dialog.result:
            name = dialog.result.get("name", "")
            value = dialog.result.get("value", "0.0")
            if name:
                try:
                    self.constants[name] = float(value)
                    self.refresh_constants_list()
                    self.status_var.set(f"Added constant: {name} = {value}")
                except ValueError:
                    messagebox.showerror("Error", "Value must be a number")
    
    def edit_constant(self):
        """Edit selected constant."""
        selection = self.constants_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a constant to edit.")
            return
        
        item = self.constants_listbox.get(selection[0])
        parts = item.split("=")
        if len(parts) >= 2:
            name = parts[0].strip()
            value = parts[1].strip()
            dialog = ConstantDialog(self.root, "Edit Constant", {"name": name, "value": value})
            if dialog.result:
                new_name = dialog.result.get("name", "")
                new_value = dialog.result.get("value", "0.0")
                if new_name:
                    try:
                        del self.constants[name]
                        self.constants[new_name] = float(new_value)
                        self.refresh_constants_list()
                        self.status_var.set(f"Updated constant: {new_name} = {new_value}")
                    except ValueError:
                        messagebox.showerror("Error", "Value must be a number")
    
    def delete_constant(self):
        """Delete selected constant."""
        selection = self.constants_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a constant to delete.")
            return
        
        item = self.constants_listbox.get(selection[0])
        parts = item.split("=")
        if len(parts) >= 1:
            name = parts[0].strip()
            if name in self.constants:
                del self.constants[name]
                self.refresh_constants_list()
                self.status_var.set(f"Deleted constant: {name}")
    
    def refresh_constants_list(self):
        """Refresh the constants listbox."""
        self.constants_listbox.delete(0, tk.END)
        for name, value in sorted(self.constants.items()):
            self.constants_listbox.insert(tk.END, f"{name} = {value}")
    
    def setup_data_input_panel(self, parent: ttk.LabelFrame):
        """Setup the right data input panel with hierarchical tree view."""
        # Create notebook for tabs
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tree view tab
        tree_frame = ttk.Frame(notebook)
        notebook.add(tree_frame, text="Hierarchy View")
        
        # Treeview with scrollbars
        tree_scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        
        self.tree = ttk.Treeview(tree_frame, columns=("Name", "Type", "Value"),
                                  yscrollcommand=tree_scroll_y.set,
                                  xscrollcommand=tree_scroll_x.set)
        
        tree_scroll_y.config(command=self.tree.yview)
        tree_scroll_x.config(command=self.tree.xview)
        
        self.tree.heading("#0", text="Item")
        self.tree.heading("Name", text="Name")
        self.tree.heading("Type", text="Type")
        self.tree.heading("Value", text="Value/Formula")
        
        self.tree.column("#0", width=200)
        self.tree.column("Name", width=150)
        self.tree.column("Type", width=100)
        self.tree.column("Value", width=300)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind double-click for editing
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        
        # Context menu
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Add Block", command=self.add_block)
        self.context_menu.add_command(label="Add Control Function", command=self.add_control_function)
        self.context_menu.add_command(label="Add Argument", command=self.add_argument)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Edit", command=self.edit_selected)
        self.context_menu.add_command(label="Delete", command=self.delete_selected)
        self.context_menu.add_command(label="Refresh", command=self.refresh_tree)
        
        self.tree.bind("<Button-3>", self.show_context_menu)
        
        # Toolbar buttons
        toolbar = ttk.Frame(tree_frame)
        toolbar.pack(fill=tk.X, pady=5)
        
        ttk.Button(toolbar, text="Add Block", command=self.add_block).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Add Function", command=self.add_control_function).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Add Argument", command=self.add_argument).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Edit", command=self.edit_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Delete", command=self.delete_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Refresh", command=self.refresh_tree).pack(side=tk.LEFT, padx=2)
    
    def show_context_menu(self, event):
        """Show context menu on right-click."""
        self.context_menu.post(event.x_root, event.y_root)
    
    def get_selected_item_info(self):
        """Get information about selected tree item."""
        selection = self.tree.selection()
        if not selection:
            return None, None, None
        
        item_id = selection[0]
        tags = self.tree.item(item_id, "tags")
        item_type = tags[0] if tags else None
        item_data = self.tree.item(item_id, "values")
        
        return item_id, item_type, item_data
    
    def add_block(self):
        """Add a new control function block."""
        dialog = BlockDialog(self.root, "New Block")
        if dialog.result:
            block = ControlFunctionBlock(dialog.result.get("name", "Unnamed"))
            self.blocks.append(block)
            self.refresh_tree()
            self.status_var.set(f"Added block: {block.name}")
    
    def add_control_function(self):
        """Add a new control function to selected block."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a block first.")
            return
        
        item_id = selection[0]
        tags = self.tree.item(item_id, "tags")
        if not tags or tags[0] != "block":
            messagebox.showwarning("Warning", "Please select a block to add a function to.")
            return
        
        block_name = self.tree.item(item_id, "text")
        block = self.find_block_by_name(block_name)
        if not block:
            return
        
        dialog = FunctionDialog(self.root, "New Control Function")
        if dialog.result:
            func = ControlFunction(
                name=dialog.result.get("name", "Unnamed"),
                initial_value=float(dialog.result.get("initial_value", "0.0")),
                formula=dialog.result.get("formula", ""),
                output_file=dialog.result.get("output_file", "")
            )
            block.add_control_function(func)
            self.func_registry[func.name] = func
            self.refresh_tree()
            self.status_var.set(f"Added function: {func.name}")
    
    def add_argument(self):
        """Add a new argument to selected control function."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a control function first.")
            return
        
        item_id = selection[0]
        tags = self.tree.item(item_id, "tags")
        if not tags or tags[0] != "function":
            messagebox.showwarning("Warning", "Please select a function to add an argument to.")
            return
        
        func_name = self.tree.item(item_id, "values")[0]
        func = self.find_function_by_name(func_name)
        if not func:
            return
        
        dialog = ArgumentDialog(self.root, "New Argument")
        if dialog.result:
            arg = Argument(
                short_name=dialog.result.get("short_name", ""),
                long_name=dialog.result.get("long_name", ""),
                module=dialog.result.get("module", ""),
                ref_type=dialog.result.get("ref_type", "object")
            )
            if dialog.result.get("data_file"):
                arg.load_data_file(dialog.result["data_file"])
            func.add_argument(arg)
            self.refresh_tree()
            self.status_var.set(f"Added argument: {arg.short_name}")
    
    def edit_selected(self):
        """Edit the selected item."""
        item_id, item_type, item_data = self.get_selected_item_info()
        if not item_id or not item_type:
            return
        
        if item_type == "block":
            dialog = BlockDialog(self.root, "Edit Block", {"name": item_data[0]})
            if dialog.result:
                block = self.find_block_by_name(item_data[0])
                if block:
                    block.name = dialog.result.get("name", block.name)
        elif item_type == "function":
            current = {
                "name": item_data[0],
                "initial_value": str(item_data[2]) if item_data[2] else "0.0",
                "formula": item_data[1] if len(item_data) > 1 else "",
                "output_file": ""
            }
            dialog = FunctionDialog(self.root, "Edit Function", current)
            if dialog.result:
                func = self.find_function_by_name(item_data[0])
                if func:
                    old_name = func.name
                    func.name = dialog.result.get("name", func.name)
                    func.initial_value = float(dialog.result.get("initial_value", "0.0"))
                    func.formula = dialog.result.get("formula", func.formula)
                    func.output_file = dialog.result.get("output_file", func.output_file)
                    # Update registry if name changed
                    if old_name != func.name:
                        del self.func_registry[old_name]
                        self.func_registry[func.name] = func
        elif item_type == "argument":
            short_name = item_data[0] if item_data else ""
            func_name = self.tree.item(self.tree.parent(item_id), "values")[0]
            func = self.find_function_by_name(func_name)
            if func:
                arg = next((a for a in func.arguments if a.short_name == short_name), None)
                if arg:
                    current = {
                        "short_name": arg.short_name,
                        "long_name": arg.long_name,
                        "module": arg.module,
                        "ref_type": arg.ref_type,
                        "data_file": arg.data_file
                    }
                    dialog = ArgumentDialog(self.root, "Edit Argument", current)
                    if dialog.result:
                        arg.short_name = dialog.result.get("short_name", arg.short_name)
                        arg.long_name = dialog.result.get("long_name", arg.long_name)
                        arg.module = dialog.result.get("module", arg.module)
                        arg.ref_type = dialog.result.get("ref_type", arg.ref_type)
                        if dialog.result.get("data_file"):
                            arg.load_data_file(dialog.result["data_file"])
        
        self.refresh_tree()
    
    def delete_selected(self):
        """Delete the selected item."""
        item_id, item_type, item_data = self.get_selected_item_info()
        if not item_id or not item_type:
            return
        
        if item_type == "block":
            block_name = item_data[0] if item_data else ""
            block = self.find_block_by_name(block_name)
            if block:
                self.blocks.remove(block)
                for func in block.control_functions:
                    if func.name in self.func_registry:
                        del self.func_registry[func.name]
        elif item_type == "function":
            func_name = item_data[0] if item_data else ""
            for block in self.blocks:
                func = next((f for f in block.control_functions if f.name == func_name), None)
                if func:
                    block.control_functions.remove(func)
                    if func.name in self.func_registry:
                        del self.func_registry[func.name]
                    break
        elif item_type == "argument":
            short_name = item_data[0] if item_data else ""
            func_name = self.tree.item(self.tree.parent(item_id), "values")[0]
            func = self.find_function_by_name(func_name)
            if func:
                func.arguments = [a for a in func.arguments if a.short_name != short_name]
        
        self.refresh_tree()
    
    def refresh_tree(self):
        """Refresh the tree view with current data."""
        self.tree.delete(*self.tree.get_children())
        
        for block in self.blocks:
            block_id = self.tree.insert("", "end", text=block.name, 
                                        values=(block.name, "Block", ""),
                                        tags=("block",))
            
            for func in block.control_functions:
                func_id = self.tree.insert(block_id, "end", text=func.name,
                                           values=(func.name, func.formula, str(func.initial_value)),
                                           tags=("function",))
                
                for arg in func.arguments:
                    arg_text = f"{arg.short_name}: {arg.long_name}"
                    if arg.data_file:
                        arg_text += f" [{os.path.basename(arg.data_file)}]"
                    self.tree.insert(func_id, "end", text=arg.short_name,
                                     values=(arg.short_name, arg.long_name, arg.ref_type),
                                     tags=("argument",))
    
    def find_block_by_name(self, name: str) -> Optional[ControlFunctionBlock]:
        """Find a block by its name."""
        for block in self.blocks:
            if block.name == name:
                return block
        return None
    
    def find_function_by_name(self, name: str) -> Optional[ControlFunction]:
        """Find a function by its name."""
        return self.func_registry.get(name)
    
    def on_tree_double_click(self, event):
        """Handle double-click on tree item."""
        self.edit_selected()
    
    def save_to_xml(self):
        """Save configuration to XML file."""
        filename = filedialog.asksaveasfilename(
            defaultextension=".xml",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
            title="Save Configuration"
        )
        
        if not filename:
            return
        
        try:
            root = ET.Element("SimulationConfig")
            
            # Save simulation parameters
            params = ET.SubElement(root, "SimulationParams")
            params.set("StartTime", self.start_time.get())
            params.set("EndTime", self.end_time.get())
            params.set("TimeStep", self.time_step.get())
            params.set("WorkDirectory", self.work_directory.get())
            params.set("SaveDate", datetime.now().isoformat())
            
            # Save constants
            constants_elem = ET.SubElement(root, "Constants")
            for name, value in self.constants.items():
                const = ET.SubElement(constants_elem, "Constant")
                const.set("Name", name)
                const.set("Value", str(value))
            
            # Save blocks
            blocks_elem = ET.SubElement(root, "ControlFuncBlocks")
            for block in self.blocks:
                blocks_elem.append(block.to_xml())
            
            # Pretty print
            xml_str = ET.tostring(root, encoding='unicode')
            dom = minidom.parseString(xml_str)
            pretty_xml = dom.toprettyxml(indent="  ")
            
            # Remove extra blank lines
            lines = pretty_xml.split('\n')
            pretty_xml = '\n'.join(line for line in lines if line.strip())
            
            with open(filename, 'w') as f:
                f.write(pretty_xml)
            
            self.status_var.set(f"Saved to: {filename}")
            messagebox.showinfo("Success", f"Configuration saved to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save XML:\n{str(e)}")
    
    def load_from_xml(self):
        """Load configuration from XML file."""
        filename = filedialog.askopenfilename(
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
            title="Load Configuration"
        )
        
        if not filename:
            return
        
        try:
            tree = ET.parse(filename)
            root = tree.getroot()
            
            # Clear current data
            self.blocks = []
            self.func_registry = {}
            self.constants = {}
            
            # Load simulation parameters
            params = root.find("SimulationParams")
            if params:
                self.start_time.set(params.get("StartTime", "0.0"))
                self.end_time.set(params.get("EndTime", "10.0"))
                self.time_step.set(params.get("TimeStep", "0.1"))
                self.work_directory.set(params.get("WorkDirectory", ""))
            
            # Load constants
            constants_elem = root.find("Constants")
            if constants_elem:
                for const_elem in constants_elem.findall("Constant"):
                    name = const_elem.get("Name", "")
                    value = const_elem.get("Value", "0.0")
                    if name:
                        self.constants[name] = float(value)
                self.refresh_constants_list()
            
            # Load blocks
            blocks_elem = root.find("ControlFuncBlocks")
            if blocks_elem:
                for block_elem in blocks_elem.findall("ControlFuncBlock"):
                    block = ControlFunctionBlock.from_xml(block_elem)
                    self.blocks.append(block)
                    for func in block.control_functions:
                        self.func_registry[func.name] = func
            
            self.refresh_tree()
            self.status_var.set(f"Loaded from: {filename}")
            messagebox.showinfo("Success", f"Configuration loaded from:\n{filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load XML:\n{str(e)}")
    
    def run_simulation(self):
        """Run the simulation."""
        try:
            start_time = float(self.start_time.get())
            end_time = float(self.end_time.get())
            dt = float(self.time_step.get())
            
            if dt <= 0:
                raise ValueError("Time step must be positive")
            if end_time <= start_time:
                raise ValueError("End time must be greater than start time")
            
            # Determine output directory
            output_dir = self.work_directory.get().strip()
            if not output_dir:
                output_dir = os.getcwd()
            
            # Open output files
            output_files = {}
            for block in self.blocks:
                for func in block.control_functions:
                    if func.output_file:
                        # If output file is relative, prepend work directory
                        if not os.path.isabs(func.output_file):
                            output_path = os.path.join(output_dir, func.output_file)
                        else:
                            output_path = func.output_file
                        # Ensure directory exists
                        output_path_dir = os.path.dirname(output_path)
                        if output_path_dir and not os.path.exists(output_path_dir):
                            os.makedirs(output_path_dir)
                        output_files[func.name] = open(output_path, 'w')
                        output_files[func.name].write("# Time\tValue\n")
            
            # Run simulation
            t = start_time
            steps = int((end_time - start_time) / dt) + 1
            
            self.status_var.set(f"Running simulation: {steps} steps...")
            self.root.update()
            
            for step in range(steps):
                t = start_time + step * dt
                
                # Evaluate all functions
                for block in self.blocks:
                    for func in block.control_functions:
                        value = func.evaluate(t, dt, self.func_registry, self.constants)
                        
                        # Write to output file
                        if func.output_file and func.name in output_files:
                            output_files[func.name].write(f"{t:.6f}\t{value:.6f}\n")
            
            # Close output files
            for f in output_files.values():
                f.close()
            
            self.status_var.set(f"Simulation completed: {steps} steps")
            messagebox.showinfo("Complete", 
                f"Simulation completed successfully!\n"
                f"Steps: {steps}\n"
                f"Time range: {start_time} to {end_time}\n"
                f"Results saved to output files in: {output_dir}")
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid parameters:\n{str(e)}")
        except Exception as e:
            messagebox.showerror("Error", f"Simulation failed:\n{str(e)}")


class BlockDialog(tk.Toplevel):
    """Dialog for creating/editing a control function block."""
    
    def __init__(self, parent, title, initial_data=None):
        super().__init__(parent)
        self.title(title)
        self.result = None
        
        self.transient(parent)
        self.grab_set()
        
        # Name
        ttk.Label(self, text="Block Name:").grid(row=0, column=0, padx=10, pady=10, sticky=tk.W)
        self.name_var = tk.StringVar(value=initial_data.get("name", "") if initial_data else "")
        ttk.Entry(self, textvariable=self.name_var, width=40).grid(row=0, column=1, padx=10, pady=10)
        
        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=1, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="OK", command=self.ok).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side=tk.LEFT, padx=10)
        
        self.wait_window(self)
    
    def ok(self):
        self.result = {"name": self.name_var.get()}
        self.destroy()
    
    def cancel(self):
        self.destroy()


class FunctionDialog(tk.Toplevel):
    """Dialog for creating/editing a control function."""
    
    def __init__(self, parent, title, initial_data=None):
        super().__init__(parent)
        self.title(title)
        self.result = None
        
        self.transient(parent)
        self.grab_set()
        
        # Name
        ttk.Label(self, text="Function Name:").grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
        self.name_var = tk.StringVar(value=initial_data.get("name", "") if initial_data else "")
        ttk.Entry(self, textvariable=self.name_var, width=50).grid(row=0, column=1, padx=10, pady=5)
        
        # Initial value
        ttk.Label(self, text="Initial Value:").grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        self.initial_var = tk.StringVar(value=initial_data.get("initial_value", "0.0") if initial_data else "0.0")
        ttk.Entry(self, textvariable=self.initial_var, width=50).grid(row=1, column=1, padx=10, pady=5)
        
        # Formula
        ttk.Label(self, text="Formula:").grid(row=2, column=0, padx=10, pady=5, sticky=tk.NW)
        self.formula_var = tk.StringVar(value=initial_data.get("formula", "") if initial_data else "")
        formula_text = tk.Text(self, width=50, height=5)
        formula_text.insert("1.0", self.formula_var.get())
        formula_text.grid(row=2, column=1, padx=10, pady=5)
        self.formula_text = formula_text
        
        # Output file
        ttk.Label(self, text="Output File:").grid(row=3, column=0, padx=10, pady=5, sticky=tk.W)
        self.output_var = tk.StringVar(value=initial_data.get("output_file", "") if initial_data else "")
        ttk.Entry(self, textvariable=self.output_var, width=40).grid(row=3, column=1, padx=10, pady=5, sticky=tk.W)
        ttk.Button(self, text="Browse", command=self.browse_file).grid(row=3, column=2, padx=5, pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=20)
        
        ttk.Button(btn_frame, text="OK", command=self.ok).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side=tk.LEFT, padx=10)
        
        self.wait_window(self)
    
    def browse_file(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".dat",
            filetypes=[("Data files", "*.dat"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            self.output_var.set(filename)
    
    def ok(self):
        self.result = {
            "name": self.name_var.get(),
            "initial_value": self.initial_var.get(),
            "formula": self.formula_text.get("1.0", tk.END).strip(),
            "output_file": self.output_var.get()
        }
        self.destroy()
    
    def cancel(self):
        self.destroy()


class ArgumentDialog(tk.Toplevel):
    """Dialog for creating/editing an argument."""
    
    def __init__(self, parent, title, initial_data=None):
        super().__init__(parent)
        self.title(title)
        self.result = None
        
        self.transient(parent)
        self.grab_set()
        
        # Short name
        ttk.Label(self, text="Short Name:").grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
        self.short_var = tk.StringVar(value=initial_data.get("short_name", "") if initial_data else "")
        ttk.Entry(self, textvariable=self.short_var, width=50).grid(row=0, column=1, padx=10, pady=5)
        
        # Long name / Reference
        ttk.Label(self, text="Long Name / Reference:").grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        self.long_var = tk.StringVar(value=initial_data.get("long_name", "") if initial_data else "")
        ttk.Entry(self, textvariable=self.long_var, width=50).grid(row=1, column=1, padx=10, pady=5)
        
        # Module
        ttk.Label(self, text="Module:").grid(row=2, column=0, padx=10, pady=5, sticky=tk.W)
        self.module_var = tk.StringVar(value=initial_data.get("module", "") if initial_data else "")
        ttk.Entry(self, textvariable=self.module_var, width=50).grid(row=2, column=1, padx=10, pady=5)
        
        # Reference type
        ttk.Label(self, text="Reference Type:").grid(row=3, column=0, padx=10, pady=5, sticky=tk.W)
        self.ref_type_var = tk.StringVar(value=initial_data.get("ref_type", "object") if initial_data else "object")
        ref_combo = ttk.Combobox(self, textvariable=self.ref_type_var, 
                                  values=["object", "t", "dt"], state="readonly", width=20)
        ref_combo.grid(row=3, column=1, padx=10, pady=5, sticky=tk.W)
        
        # Data file
        ttk.Label(self, text="Data File:").grid(row=4, column=0, padx=10, pady=5, sticky=tk.W)
        self.data_file_var = tk.StringVar(value=initial_data.get("data_file", "") if initial_data else "")
        ttk.Entry(self, textvariable=self.data_file_var, width=40).grid(row=4, column=1, padx=10, pady=5, sticky=tk.W)
        ttk.Button(self, text="Browse", command=self.browse_file).grid(row=4, column=2, padx=5, pady=5)
        
        # Info label
        info_label = ttk.Label(self, text="Data file format: two columns (time, value)", 
                               foreground="gray")
        info_label.grid(row=5, column=1, padx=10, pady=5, sticky=tk.W)
        
        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=6, column=0, columnspan=3, pady=20)
        
        ttk.Button(btn_frame, text="OK", command=self.ok).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side=tk.LEFT, padx=10)
        
        self.wait_window(self)
    
    def browse_file(self):
        filename = filedialog.askopenfilename(
            filetypes=[("Text files", "*.txt"), ("Data files", "*.dat"), ("All files", "*.*")]
        )
        if filename:
            self.data_file_var.set(filename)
    
    def ok(self):
        self.result = {
            "short_name": self.short_var.get(),
            "long_name": self.long_var.get(),
            "module": self.module_var.get(),
            "ref_type": self.ref_type_var.get(),
            "data_file": self.data_file_var.get()
        }
        self.destroy()
    
    def cancel(self):
        self.destroy()


class ConstantDialog(tk.Toplevel):
    """Dialog for creating/editing a constant."""
    
    def __init__(self, parent, title, initial_data=None):
        super().__init__(parent)
        self.title(title)
        self.result = None
        
        self.transient(parent)
        self.grab_set()
        
        # Name
        ttk.Label(self, text="Constant Name:").grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)
        self.name_var = tk.StringVar(value=initial_data.get("name", "") if initial_data else "")
        ttk.Entry(self, textvariable=self.name_var, width=40).grid(row=0, column=1, padx=10, pady=5)
        
        # Value
        ttk.Label(self, text="Value:").grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        self.value_var = tk.StringVar(value=initial_data.get("value", "0.0") if initial_data else "0.0")
        ttk.Entry(self, textvariable=self.value_var, width=40).grid(row=1, column=1, padx=10, pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="OK", command=self.ok).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side=tk.LEFT, padx=10)
        
        self.wait_window(self)
    
    def ok(self):
        self.result = {
            "name": self.name_var.get(),
            "value": self.value_var.get()
        }
        self.destroy()
    
    def cancel(self):
        self.destroy()


def main():
    """Main entry point."""
    root = tk.Tk()
    app = SimulationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
