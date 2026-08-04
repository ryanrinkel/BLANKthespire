using BaseLib.Abstracts;
using BlankTheSpire.BlankTheSpireCode.Extensions;
using Godot;

namespace BlankTheSpire.BlankTheSpireCode.Character;

public class BlankTheSpirePotionPool : CustomPotionPoolModel
{
    public override Color LabOutlineColor => BlankTheSpire.Color;
    

    public override string BigEnergyIconPath => "charui/big_energy.png".ImagePath();
    public override string TextEnergyIconPath => "charui/text_energy.png".ImagePath();
}