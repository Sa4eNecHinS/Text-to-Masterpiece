import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/utils/password.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
})
const { validateRegistrationPassword } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

for (const password of ['', 'Abc1!xy', 'abcdef1!', 'Abcdefg!', 'Abcdef12', 'Abcdef1 ', 'Abcdef1😀', 'A1!' + 'a'.repeat(70), 'A1!' + 'я'.repeat(35)]) {
  test(`rejects invalid password ${JSON.stringify(password)}`, () => {
    assert.equal(typeof validateRegistrationPassword(password), 'string')
  })
}

for (const password of ['Abcdef1!', 'ABCDEFG1_', 'Abcdef1 !', 'A1!' + 'a'.repeat(69), 'A1!' + 'я'.repeat(34)]) {
  test(`accepts valid password ${JSON.stringify(password)}`, () => {
    assert.equal(validateRegistrationPassword(password), undefined)
  })
}
