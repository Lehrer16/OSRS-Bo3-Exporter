# OSRS Bo3 Exporter

This application takes GLTF files from [OSRS Enviroment Exporter](https://github.com/ConnorDY/OSRS-Environment-Exporter) splits them into appropriate sizes and then converts them into useable models in bo3 mod tools with newly created entries in ape.


## Prerequisites

[Blender 3.6](https://www.blender.org/download/releases/3-6/) (Havent tested newer versions)

[Better Blender CoD](https://github.com/marv7000/BetterBlenderCOD) (follow installation instructions of the add-on)

## Usage

1. export model from [OSRS](https://github.com/ConnorDY/OSRS-Environment-Exporter)
2. open gltf in [Blender](https://www.blender.org/download/releases/3-6/)
3. Select all meshs you want and highlight the top one then press "ctrl + J" to join meshs into one
4. save the blender file in Bo3 Root/*New Folder*
5. rename mesh to what you would like the models to be called
6. select your mesh and run script
7. After the script completes your models should be in APE (no noeed to place "_f" versions in your map they are linked as submodel)




## Contributing

Pull requests are welcome. For major changes, please open an issue first
to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License

[MIT](https://choosealicense.com/licenses/mit/)
