#include "MrforgeAnimGraphLibrary.h"

#include "Animation/AnimBlueprint.h"
#include "AnimGraphNode_Base.h"
#include "AnimGraphNode_LinkedInputPose.h"
#include "AnimGraphNode_Root.h"
#include "AnimGraphNode_SpringBone.h"
#include "AnimationGraphSchema.h"
#include "Dom/JsonObject.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphPin.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
	UEdGraph* FindAnimGraph(UAnimBlueprint* AnimBlueprint)
	{
		for (UEdGraph* Graph : AnimBlueprint->FunctionGraphs)
		{
			if (Graph && Graph->GetSchema() && Graph->GetSchema()->IsA<UAnimationGraphSchema>() &&
				Graph->GetFName() == UEdGraphSchema_K2::GN_AnimGraph)
			{
				return Graph;
			}
		}
		return nullptr;
	}

	UEdGraphPin* PosePin(UEdGraphNode* Node, EEdGraphPinDirection Direction, bool bOnlyUnlinked)
	{
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin && Pin->Direction == Direction && !Pin->bHidden && UAnimationGraphSchema::IsPosePin(Pin->PinType) &&
				(!bOnlyUnlinked || Pin->LinkedTo.Num() == 0))
			{
				return Pin;
			}
		}
		return nullptr;
	}

	FString Title(UEdGraphNode* Node)
	{
		return FString::Printf(TEXT("%s (%s)"), *Node->GetName(), *Node->GetClass()->GetName());
	}

	FString ToJson(const TSharedRef<FJsonObject>& Obj)
	{
		FString Out;
		const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Out);
		FJsonSerializer::Serialize(Obj, Writer);
		return Out;
	}

	bool BoolAt(const TArray<TSharedPtr<FJsonValue>>* Arr, int32 Index, bool Default)
	{
		return (Arr && Arr->IsValidIndex(Index)) ? (*Arr)[Index]->AsBool() : Default;
	}
}

FString UMrforgeAnimGraphLibrary::FinishPostProcessGraph(UAnimBlueprint* AnimBlueprint, const FString& SpecJson)
{
	TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
	TArray<TSharedPtr<FJsonValue>> Messages;
	auto Fail = [&](const FString& Why)
	{
		Report->SetBoolField(TEXT("ok"), false);
		Messages.Add(MakeShared<FJsonValueString>(Why));
		Report->SetArrayField(TEXT("messages"), Messages);
		return ToJson(Report);
	};

	if (!AnimBlueprint)
	{
		return Fail(TEXT("no AnimBlueprint"));
	}
	UEdGraph* Graph = FindAnimGraph(AnimBlueprint);
	if (!Graph)
	{
		return Fail(TEXT("AnimBlueprint has no AnimGraph"));
	}
	TSharedPtr<FJsonObject> Spec;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(SpecJson);
	if (!FJsonSerializer::Deserialize(Reader, Spec) || !Spec.IsValid())
	{
		return Fail(TEXT("spec is not valid JSON"));
	}
	const UEdGraphSchema* Schema = Graph->GetSchema();

	UAnimGraphNode_Root* Root = nullptr;
	UAnimGraphNode_LinkedInputPose* Input = nullptr;
	for (UEdGraphNode* Node : Graph->Nodes)
	{
		if (UAnimGraphNode_Root* R = Cast<UAnimGraphNode_Root>(Node)) { Root = R; }
		if (UAnimGraphNode_LinkedInputPose* I = Cast<UAnimGraphNode_LinkedInputPose>(Node)) { Input = I; }
	}
	if (!Root)
	{
		return Fail(TEXT("AnimGraph has no Output Pose node"));
	}
	if (!Input)
	{
		FGraphNodeCreator<UAnimGraphNode_LinkedInputPose> Creator(*Graph);
		Input = Creator.CreateNode();
		Input->NodePosX = -800;
		Creator.Finalize();
	}
	UEdGraphPin* InputOut = PosePin(Input, EGPD_Output, false);
	if (!InputOut)
	{
		return Fail(TEXT("Input Pose node has no pose output pin"));
	}

	// Open inputs of the imported nodes come from the graph input; the imported node with an unlinked pose output
	// is the end of the vanilla graph.
	int32 InputsLinked = 0;
	TArray<UEdGraphNode*> Tails;
	int32 Imported = 0;
	for (UEdGraphNode* Node : TArray<UEdGraphNode*>(Graph->Nodes))
	{
		if (!Node || Node == Root || Node == Input || !Node->IsA<UAnimGraphNode_Base>())
		{
			continue;
		}
		++Imported;
		for (UEdGraphPin* Pin : TArray<UEdGraphPin*>(Node->Pins))
		{
			if (Pin && Pin->Direction == EGPD_Input && !Pin->bHidden && UAnimationGraphSchema::IsPosePin(Pin->PinType) &&
				Pin->LinkedTo.Num() == 0)
			{
				if (Schema->TryCreateConnection(InputOut, Pin))
				{
					++InputsLinked;
				}
				else
				{
					Messages.Add(MakeShared<FJsonValueString>(TEXT("could not link the input pose to ") + Title(Node)));
				}
			}
		}
		if (PosePin(Node, EGPD_Output, true))
		{
			Tails.Add(Node);
		}
	}
	if (Tails.Num() > 1)
	{
		FString Names;
		for (UEdGraphNode* T : Tails) { Names += Title(T) + TEXT(" "); }
		return Fail(TEXT("more than one open graph end: ") + Names);
	}
	UEdGraphPin* TailOut = Tails.Num() == 1 ? PosePin(Tails[0], EGPD_Output, true) : InputOut;
	FString TailName = Tails.Num() == 1 ? Title(Tails[0]) : TEXT("Input Pose");

	// Spring-bone chain. The anim schema inserts local<->component space conversions when a connection needs one.
	int32 Springs = 0;
	const TArray<TSharedPtr<FJsonValue>>* SpringList = nullptr;
	if (Spec->TryGetArrayField(TEXT("springs"), SpringList))
	{
		int32 X = 400;
		for (const TSharedPtr<FJsonValue>& V : *SpringList)
		{
			const TSharedPtr<FJsonObject> S = V->AsObject();
			if (!S.IsValid())
			{
				continue;
			}
			FGraphNodeCreator<UAnimGraphNode_SpringBone> Creator(*Graph);
			UAnimGraphNode_SpringBone* N = Creator.CreateNode();
			N->Node.SpringBone.BoneName = FName(*S->GetStringField(TEXT("bone")));
			double Num = 0.0;
			N->Node.SpringStiffness = S->TryGetNumberField(TEXT("stiffness"), Num) ? Num : 80.0;
			N->Node.SpringDamping = S->TryGetNumberField(TEXT("damping"), Num) ? Num : 6.0;
			N->Node.MaxDisplacement = S->TryGetNumberField(TEXT("max_displacement"), Num) ? Num : 3.0;
			N->Node.ErrorResetThresh = S->TryGetNumberField(TEXT("error_reset"), Num) ? Num : 256.0;
			bool B = true;
			N->Node.bLimitDisplacement = S->TryGetBoolField(TEXT("limit"), B) ? B : true;
			const TArray<TSharedPtr<FJsonValue>>* T = nullptr;
			const TArray<TSharedPtr<FJsonValue>>* R = nullptr;
			S->TryGetArrayField(TEXT("translate"), T);
			S->TryGetArrayField(TEXT("rotate"), R);
			N->Node.bTranslateX = BoolAt(T, 0, true);
			N->Node.bTranslateY = BoolAt(T, 1, true);
			N->Node.bTranslateZ = BoolAt(T, 2, true);
			N->Node.bRotateX = BoolAt(R, 0, false);
			N->Node.bRotateY = BoolAt(R, 1, false);
			N->Node.bRotateZ = BoolAt(R, 2, false);
			N->NodePosX = X;
			X += 300;
			Creator.Finalize();
			UEdGraphPin* In = PosePin(N, EGPD_Input, true);
			UEdGraphPin* Out = PosePin(N, EGPD_Output, true);
			if (!In || !Out || !Schema->TryCreateConnection(TailOut, In))
			{
				return Fail(TEXT("could not wire spring node for ") + S->GetStringField(TEXT("bone")));
			}
			TailOut = Out;
			TailName = Title(N);
			++Springs;
		}
	}

	UEdGraphPin* RootIn = PosePin(Root, EGPD_Input, false);
	if (!RootIn)
	{
		return Fail(TEXT("Output Pose node has no pose input pin"));
	}
	RootIn->BreakAllPinLinks();
	if (!Schema->TryCreateConnection(TailOut, RootIn))
	{
		return Fail(TEXT("could not link the graph end to the Output Pose"));
	}

	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(AnimBlueprint);
	FKismetEditorUtilities::CompileBlueprint(AnimBlueprint, EBlueprintCompileOptions::SkipGarbageCollection);
	const bool bOk = AnimBlueprint->Status == BS_UpToDate || AnimBlueprint->Status == BS_UpToDateWithWarnings;
	Report->SetBoolField(TEXT("ok"), bOk);
	Report->SetStringField(TEXT("status"), bOk ? TEXT("compiled") : TEXT("compile failed"));
	Report->SetNumberField(TEXT("imported_nodes"), Imported);
	Report->SetNumberField(TEXT("inputs_linked"), InputsLinked);
	Report->SetNumberField(TEXT("springs"), Springs);
	Report->SetNumberField(TEXT("graph_nodes"), Graph->Nodes.Num());
	Report->SetStringField(TEXT("tail"), TailName);
	Report->SetArrayField(TEXT("messages"), Messages);
	return ToJson(Report);
}

FString UMrforgeAnimGraphLibrary::DescribeAnimGraph(UAnimBlueprint* AnimBlueprint)
{
	TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
	UEdGraph* Graph = AnimBlueprint ? FindAnimGraph(AnimBlueprint) : nullptr;
	TArray<TSharedPtr<FJsonValue>> Nodes;
	if (Graph)
	{
		for (UEdGraphNode* Node : Graph->Nodes)
		{
			TSharedRef<FJsonObject> N = MakeShared<FJsonObject>();
			N->SetStringField(TEXT("node"), Title(Node));
			TArray<TSharedPtr<FJsonValue>> Links;
			for (UEdGraphPin* Pin : Node->Pins)
			{
				if (Pin && Pin->Direction == EGPD_Output && UAnimationGraphSchema::IsPosePin(Pin->PinType))
				{
					for (UEdGraphPin* L : Pin->LinkedTo)
					{
						Links.Add(MakeShared<FJsonValueString>(Title(L->GetOwningNode())));
					}
				}
			}
			N->SetArrayField(TEXT("feeds"), Links);
			Nodes.Add(MakeShared<FJsonValueObject>(N));
		}
	}
	Report->SetArrayField(TEXT("nodes"), Nodes);
	return ToJson(Report);
}
