import pathlib, shutil, subprocess, sys, tempfile, unittest
from dataclasses import asdict

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from multilang_transpiler.parser import parse
from multilang_transpiler.semantic import analyze
from multilang_transpiler.codegen import generate
from multilang_transpiler.ir import lower
from multilang_transpiler.ir import restore
from multilang_transpiler.errors import CompileError
from webapp.compiler_service import transpile as transpile_request

SAMPLES={
 'c':'#include <stdio.h>\nint main() { int n = 2; printf("%d\\n", n + 3); return 0; }',
 'python':'n = 2\nprint(n + 3)\n',
 'javascript':'let n = 2; console.log(n + 3);',
}

REGRESSION_PROGRAMS={lang:(ROOT/'samples'/f'regression.{ext}').read_text() for lang,ext in {'c':'c','python':'py','javascript':'js'}.items()}
EXPECTED_REGRESSION='Sum = 30\nGreater than 25\nProgram completed\n'

class CompilerTests(unittest.TestCase):
 def compile(self,src,dst):
  p=parse(SAMPLES[src],src); analyze(p,src); return generate(lower(p),dst)
 def test_all_nine_routes_generate(self):
  for src in SAMPLES:
   for dst in SAMPLES:
    with self.subTest(source=src,target=dst): self.assertTrue(self.compile(src,dst).strip())
 def execute(self,lang,code,d):
  if lang=='python':
   return subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True).stdout
  if lang=='javascript':
   if not shutil.which('node'): self.skipTest('node unavailable')
   return subprocess.run(['node','-e',code],capture_output=True,text=True,check=True).stdout
  cc=shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
  if not cc: self.skipTest('C compiler unavailable')
  src=pathlib.Path(d)/'prog.c'; exe=pathlib.Path(d)/'prog'; src.write_text(code)
  subprocess.run([cc,str(src),'-o',str(exe)],capture_output=True,text=True,check=True)
  return subprocess.run([str(exe)],capture_output=True,text=True,check=True).stdout
 def test_all_nine_routes_preserve_sample_output(self):
  for src in SAMPLES:
   with tempfile.TemporaryDirectory() as d:
    expected=self.execute(src,SAMPLES[src],d)
    self.assertEqual(expected,'5\n')
    for dst in SAMPLES:
     with self.subTest(source=src,target=dst), tempfile.TemporaryDirectory() as outdir:
      self.assertEqual(self.execute(dst,self.compile(src,dst),outdir),expected)

 def test_professor_regressions_cover_all_nine_routes_and_runtime_output(self):
  for source, source_code in REGRESSION_PROGRAMS.items():
   with tempfile.TemporaryDirectory() as directory:
    self.assertEqual(self.execute(source,source_code,directory),EXPECTED_REGRESSION)
   for target in REGRESSION_PROGRAMS:
    with self.subTest(source=source,target=target), tempfile.TemporaryDirectory() as directory:
     program=parse(source_code,source); analyze(program,source)
     generated=generate(lower(program),target)
     self.assertEqual(self.execute(target,generated,directory),EXPECTED_REGRESSION)

 def test_professor_regression_false_branch_in_all_targets(self):
  variants={
   'c':REGRESSION_PROGRAMS['c'].replace('int b = 20;', 'int b = 10;'),
   'python':REGRESSION_PROGRAMS['python'].replace('b = 20', 'b = 10'),
   'javascript':REGRESSION_PROGRAMS['javascript'].replace('let b = 20;', 'let b = 10;'),
  }
  expected='Sum = 20\n25 or less\nProgram completed\n'
  for source,source_code in variants.items():
   for target in REGRESSION_PROGRAMS:
    with self.subTest(source=source,target=target), tempfile.TemporaryDirectory() as directory:
     program=parse(source_code,source); analyze(program,source)
     self.assertEqual(self.execute(target,generate(lower(program),target),directory),expected)

 def test_print_multiple_arguments_nested_expressions_and_string_inference_to_c(self):
  sources={
   'python':'def twice(value):\n    return value * 2\nlabel = "Result ="\nprint(label, twice(2 + 3))\n',
   'javascript':'function twice(value) { return value * 2; }\nlet label = "Result =";\nconsole.log(label, twice(2 + 3));\n'
  }
  for source,source_code in sources.items():
   for target in ('c','python','javascript'):
    with self.subTest(source=source,target=target), tempfile.TemporaryDirectory() as directory:
     program=parse(source_code,source); analyze(program,source)
     self.assertEqual(self.execute(target,generate(lower(program),target),directory),'Result = 10\n')

 def test_unknown_python_value_type_has_clear_c_diagnostic(self):
  program=parse('value = None\nprint(value)\n','python'); analyze(program,'python')
  with self.assertRaisesRegex(CompileError,'cannot safely infer'):
   generate(lower(program),'c')
 def test_python_target_is_valid_and_runs(self):
  code=self.compile('c','python')
  proc=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True)
  self.assertEqual(proc.stdout,'5\n')
 def test_javascript_target_is_valid_and_runs(self):
  if not shutil.which('node'): self.skipTest('node unavailable')
  code=self.compile('python','javascript')
  proc=subprocess.run(['node','-e',code],capture_output=True,text=True,check=True)
  self.assertEqual(proc.stdout,'5\n')
 def test_c_target_is_valid_and_runs(self):
  cc=shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
  if not cc: self.skipTest('C compiler unavailable')
  with tempfile.TemporaryDirectory() as d:
   src=pathlib.Path(d)/'main.c'; exe=pathlib.Path(d)/'run'; src.write_text(self.compile('javascript','c'))
   subprocess.run([cc,str(src),'-o',str(exe)],capture_output=True,text=True,check=True)
   proc=subprocess.run([str(exe)],capture_output=True,text=True,check=True)
   self.assertEqual(proc.stdout,'5\n')
 def test_c_array_counted_loop_function_and_printf_matrix(self):
  source='''#include <stdio.h>\nint square(int n) { return n * n; }\nint main() {\n int numbers[5] = {2, 4, 6, 8, 10};\n int sum = 0;\n int i = 0;\n for (i = 0; i < 5; i++) { sum += square(numbers[i]); }\n printf(\"sum=%d\\n\", sum);\n return 0;\n}'''
  program=parse(source,'c'); analyze(program,'c')
  for target in SAMPLES:
   with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
    generated=generate(lower(program),target)
    self.assertEqual(self.execute(target,generated,directory),'sum=220\n')

 def test_array_programs_preserve_output_across_all_nine_routes(self):
  sources={
   'c':'''#include <stdio.h>\nint square(int n) { return n * n; }\nint main() { int values[3] = {2, 3, 4}; int total = 0; int i = 0; for (i = 0; i < 3; i++) { total += square(values[i]); } printf(\"%d\\n\", total); return 0; }''',
   'python':'def square(n):\n    return n * n\nvalues = [2, 3, 4]\ntotal = 0\nfor i in range(3):\n    total += square(values[i])\nprint(total)\n',
   'javascript':'function square(n) { return n * n; } let values = [2, 3, 4]; let total = 0; for (let i = 0; i < 3; i++) { total += square(values[i]); } console.log(total);'
  }
  for source,code in sources.items():
   with tempfile.TemporaryDirectory() as source_dir:
    expected=self.execute(source,code,source_dir)
   self.assertEqual(expected,'29\n')
   for target in SAMPLES:
    with self.subTest(source=source,target=target), tempfile.TemporaryDirectory() as directory:
     program=parse(code,source); analyze(program,source)
     self.assertEqual(self.execute(target,generate(lower(program),target),directory),expected)

 def test_python_blank_and_comment_lines_inside_blocks(self):
  source='''def choose(value):\n    # ignore this comment-only line\n\n    if value == 2:\n        # comment in branch\n\n        return 7\n    return 0\n\nprint(choose(2))\n'''
  program=parse(source,'python'); analyze(program,'python')
  for target in SAMPLES:
   with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
    self.assertEqual(self.execute(target,generate(lower(program),target),directory),'7\n')

 def test_c_void_main_and_multiline_block_comments(self):
  source='''#include <stdio.h>\nint main(void) { /* opening comment\n   continuation */ int x = 4; printf(\"%d\\n\", x); return 0; }\n'''
  program=parse(source,'c'); analyze(program,'c')
  for target in SAMPLES:
   with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
    self.assertEqual(self.execute(target,generate(lower(program),target),directory),'4\n')

 def test_else_if_and_elif_routes(self):
  sources={
   'c':'''#include <stdio.h>\nint main(void) { int x = 2; if (x == 1) { printf(\"one\\n\"); } else if (x == 2) { printf(\"two\\n\"); } else { printf(\"other\\n\"); } return 0; }''',
   'python':'x = 2\nif x == 1:\n    print("one")\nelif x == 2:\n    print("two")\nelse:\n    print("other")\n',
   'javascript':'let x = 2; if (x == 1) { console.log("one"); } else if (x == 2) { console.log("two"); } else { console.log("other"); }'
  }
  for source,code in sources.items():
   program=parse(code,source); analyze(program,source)
   for target in SAMPLES:
    with self.subTest(source=source,target=target), tempfile.TemporaryDirectory() as directory:
     self.assertEqual(self.execute(target,generate(lower(program),target),directory),'two\n')

 def test_multiple_declarations_in_one_statement(self):
  source='''#include <stdio.h>\nint main(void) { int a = 2, b = 3; printf(\"%d\\n\", a + b); return 0; }'''
  program=parse(source,'c'); analyze(program,'c')
  for target in SAMPLES:
   with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
    self.assertEqual(self.execute(target,generate(lower(program),target),directory),'5\n')

 def test_c_target_rejects_dynamic_type_changes(self):
  program=parse('value = 1\nvalue = "text"\nprint(value)\n','python'); analyze(program,'python')
  with self.assertRaisesRegex(CompileError,'changes from int to string'):
   generate(lower(program),'c')

 def test_output_arguments_validate_missing_and_extra_printf_values(self):
  for code in ('printf();','printf("%d",);'):
   with self.subTest(code=code), self.assertRaises(CompileError): parse(code,'c')
  program=parse('printf("%d", 1, 2);','c'); analyze(program,'c')
  with self.assertRaisesRegex(CompileError,'format has 1 supported'):
   generate(lower(program),'python')

 def test_unsupported_construct_reports_a_syntax_diagnostic(self):
  with self.assertRaisesRegex(CompileError,'unsupported statement'):
   parse('switch (value) { }','c')

 def test_output_argument_syntax_empty_calls_and_trailing_comma(self):
  for language, source in (('python','print("ok",)'),('javascript','console.log("ok",);')):
   with self.subTest(language=language):
    program=parse(source,language); analyze(program,language)
    self.assertEqual(self.execute('python',generate(lower(program),'python'),tempfile.gettempdir()),'ok\n')
  self.assertEqual(self.execute('python',generate(lower(parse('print()','python')),'python'),tempfile.gettempdir()),'\n')
  with self.assertRaisesRegex(CompileError,'format string'):
   parse('printf();','c')
  with self.assertRaises(CompileError): parse('printf("%d",);','c')

 def test_arithmetic_precedence_across_sources_and_targets(self):
  sources={
   'c':'#include <stdio.h>\nint main(void) { printf("%d\\n", 2 + 3 * 4); return 0; }',
   'python':'print(2 + 3 * 4)\n',
   'javascript':'console.log(2 + 3 * 4);'
  }
  for source,code in sources.items():
   program=parse(code,source); analyze(program,source)
   for target in REGRESSION_PROGRAMS:
    with self.subTest(source=source,target=target):
     self.assertEqual(self.execute(target,generate(lower(program),target),tempfile.gettempdir()),'14\n')

 def test_c_integer_division_rounds_toward_zero_after_translation(self):
  source='#include <stdio.h>\nint main(void) { int value = -3 / 2; printf("%d\\n", value); return 0; }'
  program=parse(source,'c'); analyze(program,'c')
  for target in ('python','javascript'):
   with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
    self.assertEqual(self.execute(target,generate(lower(program),target),directory),'-1\n')

 def test_c_main_return_status_is_preserved_in_other_runtimes(self):
  source='#include <stdio.h>\nint main(void) { printf("done\\n"); return 4; }'
  program=parse(source,'c'); analyze(program,'c')
  for target in ('python','javascript'):
   generated=generate(lower(program),target)
   with self.subTest(target=target):
    if target=='python': proc=subprocess.run([sys.executable,'-c',generated],capture_output=True,text=True)
    else: proc=subprocess.run(['node','-e',generated],capture_output=True,text=True)
    self.assertEqual(proc.stdout,'done\n')
    self.assertEqual(proc.returncode,4)

 def test_javascript_const_requires_initializer_and_rejects_reassignment(self):
  with self.assertRaisesRegex(CompileError,'require an initializer'):
   parse('const value;','javascript')
  program=parse('const value = 3; value = 4;','javascript')
  with self.assertRaisesRegex(CompileError,'cannot assign to constant'):
   analyze(program,'javascript')

 def test_lexical_error_has_line(self):
  with self.assertRaisesRegex(CompileError,'line 2'): parse('int x = 1;\n@','c')
 def test_syntax_error_is_reported(self):
  with self.assertRaises(CompileError): parse('int x = ;','c')
 def test_semantic_error_is_reported(self):
  p=parse('x = 4;','c')
  with self.assertRaisesRegex(CompileError,'undeclared'): analyze(p,'c')
 def test_unindented_python_block_errors(self):
  with self.assertRaises(CompileError): parse('if True:\nprint(1)\n','python')
 def test_unsupported_c_directive_is_rejected(self):
  with self.assertRaisesRegex(CompileError,'preprocessing error'): parse('#define X 2\nint n = 1;','c')
 def test_while_loop_runs_after_transpilation(self):
  src='i = 0\ntotal = 0\nwhile i < 3:\n    total = total + i\n    i = i + 1\nprint(total)\n'
  p=parse(src,'python'); analyze(p,'python')
  self.assertEqual(self.execute('javascript',generate(lower(p),'javascript'),tempfile.gettempdir()),'3\n')
 def test_function_runs_after_transpilation(self):
  src='def twice(x):\n    return x * 2\nprint(twice(4))\n'
  p=parse(src,'python'); analyze(p,'python')
  self.assertEqual(self.execute('javascript',generate(lower(p),'javascript'),tempfile.gettempdir()),'8\n')
 def test_if_while_and_function_samples_preserve_output_across_matrix(self):
  extensions={'c':'c','python':'py','javascript':'js'}
  expected={'if_else':'5\n','while_loop':'3\n','function':'8\n'}
  for sample,want in expected.items():
   for source in extensions:
    code=(ROOT/'samples'/f'{sample}.{extensions[source]}').read_text()
    for target in extensions:
     with self.subTest(sample=sample,source=source,target=target):
      program=parse(code,source); analyze(program,source); output=generate(lower(program),target)
      with tempfile.TemporaryDirectory() as directory:
       if target=='python':
        actual=subprocess.run([sys.executable,'-c',output],capture_output=True,text=True,check=True).stdout
       elif target=='javascript':
        actual=subprocess.run(['node','-e',output],capture_output=True,text=True,check=True).stdout
       else:
        compiler=shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
        if not compiler: self.skipTest('C compiler unavailable')
        cfile=pathlib.Path(directory)/'main.c'; executable=pathlib.Path(directory)/'main'; cfile.write_text(output)
        subprocess.run([compiler,str(cfile),'-o',str(executable)],capture_output=True,text=True,check=True)
        actual=subprocess.run([str(executable)],capture_output=True,text=True,check=True).stdout
      self.assertEqual(actual,want)
 def test_printf_without_arguments_preserves_newline_across_targets(self):
  program=parse('printf("Hello\\n");','c'); analyze(program,'c')
  for target in SAMPLES:
   with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
    self.assertEqual(self.execute(target,generate(lower(program),target),directory),'Hello\n')

 def test_printf_without_newline_and_percent_escape_across_targets(self):
  source='''#include <stdio.h>\nint main(void) { printf(\"100%% %d\", 7); return 0; }'''
  program=parse(source,'c'); analyze(program,'c')
  for target in REGRESSION_PROGRAMS:
   with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
    self.assertEqual(self.execute(target,generate(lower(program),target),directory),'100% 7')

 def test_println_string_alias_generates_real_output(self):
  program=parse('println("Hello");','c'); analyze(program,'c')
  with tempfile.TemporaryDirectory() as directory:
   for target in ('python','javascript','c'):
    with self.subTest(target=target): self.assertEqual(self.execute(target,generate(lower(program),target),directory),'Hello\n')
 def test_unknown_function_is_a_semantic_error(self):
  program=parse('mystery(1);','c')
  with self.assertRaisesRegex(CompileError,'unknown function'): analyze(program,'c')

 def test_function_call_argument_count_is_checked_semantically(self):
  cases=(
   ('def add(left, right):\n    return left + right\nprint(add(1))\n','python',"expects 2 argument(s), got 1"),
   ('function show(value) { return value; } show();','javascript',"expects 1 argument(s), got 0"),
   ('int add(int left, int right) { return left + right; } int main(void) { return add(1, 2, 3); }','c',"expects 2 argument(s), got 3"),
  )
  for source,language,message in cases:
   with self.subTest(language=language), self.assertRaises(CompileError) as raised:
    analyze(parse(source,language),language)
   self.assertIn(message,str(raised.exception))

 def test_compiler_service_returns_arity_error_without_generated_output(self):
  source='def add(left, right):\n    return left + right\nprint(add(1))\n'
  result=transpile_request('python','javascript',source)
  self.assertFalse(result['success'])
  self.assertIsNone(result['generated_code'])
  self.assertEqual(result['error']['phase'],'semantic')
  self.assertEqual(result['error']['line'],3)

 def test_ir_is_operation_based_distinct_and_round_trips_to_ast(self):
  source='def twice(value):\n    return value * 2\nnumber = 3\nprint(twice(number + 1))\n'
  program=parse(source,'python')
  analyze(program,'python')
  ir=lower(program)
  self.assertEqual(ir['ir_version'],2)
  self.assertEqual(ir['body'][0]['op'],'FUNCTION')
  self.assertEqual(ir['body'][1]['op'],'DECLARE_VARIABLE')
  self.assertEqual(ir['body'][2]['op'],'OUTPUT')
  self.assertNotIn('kind',ir['body'][0])
  self.assertEqual(asdict(restore(ir)),asdict(program))
  legacy={'ir_version':1,'source_language':'python','body':[asdict(statement) for statement in program.body]}
  self.assertEqual(asdict(restore(legacy)),asdict(program))

 def test_dashboard_phase_payloads_show_actual_ast_semantics_and_ir(self):
  source='def twice(value):\n    return value * 2\nnumber = 3\nprint(twice(number + 1))\n'
  result=transpile_request('python','javascript',source)
  self.assertTrue(result['success'],result)
  phases={phase['id']:phase for phase in result['phases']}
  self.assertEqual(phases['ast']['output']['tree'],result['ast'])
  self.assertIn('Abstract Syntax Tree',phases['ast']['output']['explanation'])
  self.assertEqual(phases['semantic']['output']['status'],'passed')
  self.assertIn('number',{symbol['name'] for symbol in phases['semantic']['output']['symbols']})
  self.assertEqual(phases['semantic']['output']['functions'][0]['name'],'twice')
  self.assertEqual(phases['ir']['output'],result['ir'])
  self.assertEqual(result['ir']['body'][0]['op'],'FUNCTION')
  self.assertNotEqual(phases['ast']['output']['tree']['body'][0]['kind'],result['ir']['body'][0]['op'])
  self.assertTrue(all(phase.get('description') for phase in result['phases']))

 def test_duplicate_function_definitions_are_rejected(self):
  source='def repeat(value):\n    return value\ndef repeat(other):\n    return other\n'
  with self.assertRaisesRegex(CompileError,'duplicate function definition'):
   analyze(parse(source,'python'),'python')

 def test_markdown_fences_report_a_helpful_preprocessing_error(self):
  for language in SAMPLES:
   with self.subTest(language=language), self.assertRaisesRegex(CompileError,'Markdown code fences are not source code'):
    parse('```'+language+'\nprint(1)\n```',language)

if __name__=='__main__': unittest.main()
