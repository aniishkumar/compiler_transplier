const fs = require('fs');
let _inputBuf = '';
function prompt() {
    while (true) {
        let _start = 0;
        while (_start < _inputBuf.length && _inputBuf.charCodeAt(_start) <= 32) {
            _start = _start + 1;
        }
        if (_start < _inputBuf.length) {
            let _end = _start;
            while (_end < _inputBuf.length && _inputBuf.charCodeAt(_end) > 32) {
                _end = _end + 1;
            }
            let token = _inputBuf.slice(_start, _end);
            _inputBuf = _inputBuf.slice(_end);
            return token;
        }
        let buf = Buffer.alloc(1024);
        let n = fs.readSync(0, buf, 0, 1024);
        if (n == 0) {
            return '';
        }
        _inputBuf = _inputBuf + buf.toString('utf-8', 0, n);
    }
    return '';
}
class Student {
    constructor(id = 0, name = "", marks = 0.0) {
        this.id = id;
        this.name = name;
        this.marks = marks;
    }
}

function main() {
    let n = { value: 0 };
    process.stdout.write(require("util").format("Enter number of students: "));
    n.value = parseInt(prompt() || '0', 10);
    let ptr = null;
    ptr = Array.from({ length: n.value }, () => new Student());
    if ((ptr == null)) {
        process.stdout.write(require("util").format("Memory allocation failed!"));
        return 1;
    }
    for (let i = 0; (i < n.value); i++) {
        console.log("\nEnter details for student %d", (i + 1));
        process.stdout.write(require("util").format("Enter ID: "));
        ptr[i].id = parseInt(prompt() || '0', 10);
        process.stdout.write(require("util").format("Enter Name: "));
        ptr[i].name = prompt() || '';
        process.stdout.write(require("util").format("Enter Marks: "));
        ptr[i].marks = parseFloat(prompt() || '0');
    }
    console.log("\n----- Student Records -----");
    for (let i = 0; (i < n.value); i++) {
        process.stdout.write(require("util").format("\nID: %d", ptr[i].id));
        process.stdout.write(require("util").format("\nName: %s", ptr[i].name));
        console.log("\nMarks: %s", Number(ptr[i].marks).toFixed(2));
    }
    ptr = null;
    console.log("\nMemory freed successfully!");
    return 0;
}
process.exitCode = main();
