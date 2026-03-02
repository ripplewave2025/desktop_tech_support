Need to have a full app ui chat interface hoverable and they can place wherever they like somewhat transparent not covering the whole screen tho, shows thinking as well and actions as well while describing what they are doing. It should be able to be pinned to top, bottom, left, or right of the screen.
It automatically pulls ollama free AI while installing (later with claude/openai) and works with the available tools in the windows
for the hardware and other things it should use the manufacturers app if available else it should use the available tools in the windows
It should have a feature to take screenshot and analyze it and provide suggestions to fix the issue and also should be able to take actions on the screenshot with user permission.
lets just first start with the ui and the basic features and then we can add more features later. Like updating the browser, and reinstalling the drivers by going to device manager uninstall and restarting the computer for audio drivers.which usually works.


worked with ollama 
installed ollama pull moondream         as gemini said that this is the workable model for my cpu
Download the Vision Model: Open your command prompt and run:
ollama pull moondream

Install Open Interpreter: Ensure you have Python installed, then run:
pip install open-interpreter

Launch it in OS Mode: Tell it to use your local Moondream model and activate mouse control:
interpreter --model ollama/moondream --os